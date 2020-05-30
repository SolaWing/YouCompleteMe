# flake8: noqa: E501
# Copyright (C) 2011-2018 YouCompleteMe contributors
#
# This file is part of YouCompleteMe.
#
# YouCompleteMe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# YouCompleteMe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with YouCompleteMe.  If not, see <http://www.gnu.org/licenses/>.

import base64
import json
import logging
import os
import re
import signal
import vim
from subprocess import PIPE
from time import time
from tempfile import NamedTemporaryFile
from ycm import base, paths, signature_help, vimsupport
from ycm.buffer import BufferDict
from ycmd import utils
from ycmd.request_wrap import RequestWrap
from ycm.omni_completer import OmniCompleter
from ycm import syntax_parse
from ycm.client.ycmd_keepalive import YcmdKeepalive
from ycm.client.base_request import BaseRequest, BuildRequestData
from ycm.client.completer_available_request import SendCompleterAvailableRequest
from ycm.client.command_request import SendCommandRequest, GetCommandResponse
from ycm.client.completion_request import CompletionRequest
from ycm.client.signature_help_request import ( SignatureHelpRequest,
                                                SigHelpAvailableByFileType )
from ycm.client.debug_info_request import ( SendDebugInfoRequest,
                                            FormatDebugInfoResponse )
from ycm.client.omni_completion_request import OmniCompletionRequest
from ycm.client.event_notification import SendEventNotificationAsync
from ycm.client.shutdown_request import SendShutdownRequest
from ycm.client.messages_request import MessagesPoll


def PatchNoProxy():
  current_value = os.environ.get( 'no_proxy', '' )
  additions = '127.0.0.1,localhost'
  os.environ[ 'no_proxy' ] = ( additions if not current_value
                               else current_value + ',' + additions )


# We need this so that Requests doesn't end up using the local HTTP proxy when
# talking to ycmd. Users should actually be setting this themselves when
# configuring a proxy server on their machine, but most don't know they need to
# or how to do it, so we do it for them.
# Relevant issues:
#  https://github.com/Valloric/YouCompleteMe/issues/641
#  https://github.com/kennethreitz/requests/issues/879
PatchNoProxy()

# Force the Python interpreter embedded in Vim (in which we are running) to
# ignore the SIGINT signal. This helps reduce the fallout of a user pressing
# Ctrl-C in Vim.
signal.signal( signal.SIGINT, signal.SIG_IGN )

HMAC_SECRET_LENGTH = 16
SERVER_SHUTDOWN_MESSAGE = (
  "The ycmd server SHUT DOWN (restart with ':YcmRestartServer')." )
EXIT_CODE_UNEXPECTED_MESSAGE = (
  "Unexpected exit code {code}. "
  "Type ':YcmToggleLogs {logfile}' to check the logs." )
CORE_UNEXPECTED_MESSAGE = (
  "Unexpected error while loading the YCM core library. "
  "Type ':YcmToggleLogs {logfile}' to check the logs." )
CORE_MISSING_MESSAGE = (
  'YCM core library not detected; you need to compile YCM before using it. '
  'Follow the instructions in the documentation.' )
CORE_OUTDATED_MESSAGE = (
  'YCM core library too old; PLEASE RECOMPILE by running the install.py '
  'script. See the documentation for more details.' )
NO_PYTHON2_SUPPORT_MESSAGE = (
  'YCM has dropped support for python2. '
  'You need to recompile it with python3 instead.' )
SERVER_IDLE_SUICIDE_SECONDS = 1800  # 30 minutes
CLIENT_LOGFILE_FORMAT = 'ycm_'
SERVER_LOGFILE_FORMAT = 'ycmd_{port}_{std}_'

# Flag to set a file handle inheritable by child processes on Windows. See
# https://msdn.microsoft.com/en-us/library/ms724935.aspx
HANDLE_FLAG_INHERIT = 0x00000001


class YouCompleteMe:
  def __init__( self ):
    self._available_completers = {}
    self._user_options = None
    self._user_notified_about_crash = False
    self._omnicomp = None
    self._buffers = None
    self._latest_completion_request = None
    self._latest_signature_help_request = None
    self._signature_help_available_requests = SigHelpAvailableByFileType()
    self._signature_help_state = signature_help.SignatureHelpState()
    self._logger = logging.getLogger( 'ycm' )
    self._client_logfile = None
    self._server_stdout = None
    self._server_stderr = None
    self._server_popen = None
    self._filetypes_with_keywords_loaded = set()
    self._ycmd_keepalive = YcmdKeepalive()
    self._server_is_ready_with_cache = False
    self._SetUpLogging()
    self._SetUpServer()
    self._ycmd_keepalive.Start()

    clang_param_expand = self._OnCompleteDone_Clang
    self._complete_really_done = False
    self._complete_done_hooks = {
           'c': clang_param_expand,
         'cpp': clang_param_expand,
        'objc': clang_param_expand,
      'objcpp': clang_param_expand,
       'swift': self._OnCompleteDone_Swift,
           '*': self._OnCompleteDone_UltiSnip,
    }
    import tempfile
    self._used_completions = UsedCompletions( os.path.join(tempfile.gettempdir(), "ycm_used_completions.sqlite") )
    self._saw_completions  = SawCompletions()

  def _SetUpServer( self ):
    self._available_completers = {}
    self._user_notified_about_crash = False
    self._filetypes_with_keywords_loaded = set()
    self._server_is_ready_with_cache = False
    self._message_poll_requests = {}

    self._user_options = base.GetUserOptions()
    self._omnicomp = OmniCompleter( self._user_options )
    self._buffers = BufferDict( self._user_options )

    self._SetLogLevel()

    hmac_secret = os.urandom( HMAC_SECRET_LENGTH )
    options_dict = dict( self._user_options )
    options_dict[ 'hmac_secret' ] = utils.ToUnicode(
      base64.b64encode( hmac_secret ) )
    options_dict[ 'server_keep_logfiles' ] = self._user_options[
      'keep_logfiles' ]

    # The temp options file is deleted by ycmd during startup.
    with NamedTemporaryFile( delete = False, mode = 'w+' ) as options_file:
      json.dump( options_dict, options_file )

    server_port = utils.GetUnusedLocalhostPort()

    BaseRequest.server_location = 'http://127.0.0.1:' + str( server_port )
    BaseRequest.hmac_secret = hmac_secret

    try:
      python_interpreter = paths.PathToPythonInterpreter()
    except RuntimeError as error:
      error_message = (
        "Unable to start the ycmd server. {0}. "
        "Correct the error then restart the server "
        "with ':YcmRestartServer'.".format( str( error ).rstrip( '.' ) ) )
      self._logger.exception( error_message )
      vimsupport.PostVimMessage( error_message )
      return

    args = [ python_interpreter,
             paths.PathToServerScript(),
             '--port={0}'.format( server_port ),
             '--options_file={0}'.format( options_file.name ),
             '--log={0}'.format( self._user_options[ 'log_level' ] ),
             '--idle_suicide_seconds={0}'.format(
                SERVER_IDLE_SUICIDE_SECONDS ) ]

    self._server_stdout = utils.CreateLogfile(
        SERVER_LOGFILE_FORMAT.format( port = server_port, std = 'stdout' ) )
    self._server_stderr = utils.CreateLogfile(
        SERVER_LOGFILE_FORMAT.format( port = server_port, std = 'stderr' ) )
    args.append( '--stdout={0}'.format( self._server_stdout ) )
    args.append( '--stderr={0}'.format( self._server_stderr ) )

    if self._user_options[ 'keep_logfiles' ]:
      args.append( '--keep_logfiles' )

    self._server_popen = utils.SafePopen( args, stdin_windows = PIPE,
                                          stdout = PIPE, stderr = PIPE )


  def _SetUpLogging( self ):
    def FreeFileFromOtherProcesses( file_object ):
      if utils.OnWindows():
        from ctypes import windll
        import msvcrt

        file_handle = msvcrt.get_osfhandle( file_object.fileno() )
        windll.kernel32.SetHandleInformation( file_handle,
                                              HANDLE_FLAG_INHERIT,
                                              0 )

    self._client_logfile = utils.CreateLogfile( CLIENT_LOGFILE_FORMAT )

    handler = logging.FileHandler( self._client_logfile )

    # On Windows and Python prior to 3.4, file handles are inherited by child
    # processes started with at least one replaced standard stream, which is the
    # case when we start the ycmd server (we are redirecting all standard
    # outputs into a pipe). These files cannot be removed while the child
    # processes are still up. This is not desirable for a logfile because we
    # want to remove it at Vim exit without having to wait for the ycmd server
    # to be completely shut down. We need to make the logfile handle
    # non-inheritable. See https://www.python.org/dev/peps/pep-0446 for more
    # details.
    FreeFileFromOtherProcesses( handler.stream )

    formatter = logging.Formatter( '%(asctime)s - %(levelname)s - %(message)s' )
    handler.setFormatter( formatter )

    self._logger.addHandler( handler )


  def _SetLogLevel( self ):
    log_level = self._user_options[ 'log_level' ]
    numeric_level = getattr( logging, log_level.upper(), None )
    if not isinstance( numeric_level, int ):
      raise ValueError( 'Invalid log level: {0}'.format( log_level ) )
    self._logger.setLevel( numeric_level )


  def IsServerAlive( self ):
    # When the process hasn't finished yet, poll() returns None.
    return bool( self._server_popen ) and self._server_popen.poll() is None


  def CheckIfServerIsReady( self ):
    if not self._server_is_ready_with_cache and self.IsServerAlive():
      self._server_is_ready_with_cache = BaseRequest().GetDataFromHandler(
          'ready', display_message = False )
    return self._server_is_ready_with_cache


  def IsServerReady( self ):
    return self._server_is_ready_with_cache


  def NotifyUserIfServerCrashed( self ):
    if ( not self._server_popen or self._user_notified_about_crash or
         self.IsServerAlive() ):
      return
    self._user_notified_about_crash = True

    return_code = self._server_popen.poll()
    logfile = os.path.basename( self._server_stderr )
    # See https://github.com/Valloric/ycmd#exit-codes for the list of exit
    # codes.
    if return_code == 3:
      error_message = CORE_UNEXPECTED_MESSAGE.format( logfile = logfile )
    elif return_code == 4:
      error_message = CORE_MISSING_MESSAGE
    elif return_code == 7:
      error_message = CORE_OUTDATED_MESSAGE
    elif return_code == 8:
      error_message = NO_PYTHON2_SUPPORT_MESSAGE
    else:
      error_message = EXIT_CODE_UNEXPECTED_MESSAGE.format( code = return_code,
                                                           logfile = logfile )

    if return_code != 8:
      error_message = SERVER_SHUTDOWN_MESSAGE + ' ' + error_message
    self._logger.error( error_message )
    vimsupport.PostVimMessage( error_message )


  def ServerPid( self ):
    if not self._server_popen:
      return -1
    return self._server_popen.pid


  def _ShutdownServer( self ):
    SendShutdownRequest()


  def RestartServer( self ):
    vimsupport.PostVimMessage( 'Restarting ycmd server...' )
    self._ShutdownServer()
    self._SetUpServer()


  def SendCompletionRequest( self, force_semantic = False ):
    request_data = BuildRequestData()
    request_data[ 'force_semantic' ] = force_semantic

    if not self.NativeFiletypeCompletionUsable():
      wrapped_request_data = RequestWrap( request_data )
      if self._omnicomp.ShouldUseNow( wrapped_request_data ):
        self._latest_completion_request = OmniCompletionRequest(
            self._omnicomp, wrapped_request_data )
        self._latest_completion_request.Start()
        return

    self._AddExtraConfDataIfNeeded( request_data )
    self._latest_completion_request = CompletionRequest( request_data )
    self._latest_completion_request.Start()


  def CompletionRequestReady( self ):
    return bool( self._latest_completion_request and
                 self._latest_completion_request.Done() )


  def GetCompletionResponse( self ):
    response = self._latest_completion_request.Response()
    response[ 'completions' ] = self._SortByUsage(
        response[ 'completions' ],
        self._saw_completions.saw(self._latest_completion_request, response))
    self._saw_completions.see(self._latest_completion_request, response)
    response[ 'completions' ] = base.AdjustCandidateInsertionText(
        response[ 'completions' ] )
    response[ 'completions' ] = self._prependNumber(response['completions'])
    return response

  def _SortByUsage( self, completions, saw_words ):
    if not completions: return completions
    # logging.getLogger( 'ycm' ).info("saw_words %s", saw_words) # type: logging.Logger

    max_sort_num = min(30, len(completions))
    scores = self._used_completions.scoresFor([w for w in (c['word'] for c in completions[:max_sort_num])
                                               if w not in saw_words],
                                              time())

    # logging.getLogger( 'ycm' ).info("scores %s", scores) # type: logging.Logger

    recent_count = 1
    if len(scores) > 0:
      def score_at(i):
        w = completions[i]['word']
        return scores.get(w, 0)

      def less(i, j):
        return score_at(i) < score_at(j)

      for c in range(recent_count):
        maxi = c
        for i in range(c+1, max_sort_num):
          if less(maxi, i): maxi = i

        if maxi > c:
          #  self._logger.debug("move %d to %d", maxi, c)
          completions.insert(c, completions.pop(maxi))

    # sort by saw_words, seems less useful after second completions
    # unsaw = 0
    # for i in range(max_sort_num):
    #     if completions[i]['word'] not in saw_words:
    #         if i > unsaw:
    #             completions.insert(unsaw, completions.pop(i))
    #         if unsaw == 1: break
    #         unsaw += 1

    return completions


  def _prependNumber(self, completions):
      for (i, c) in enumerate(completions):
          # print(type(c), c)
          c['abbr'] = "%d: %s"%(i+1, c.get('abbr', c['word']))
      return completions

  def SignatureHelpAvailableRequestComplete( self, filetype, send_new=True ):
    """Triggers or polls signature help available request. Returns whether or
    not the request is complete. When send_new is False, won't send a new
    request, only return the current status (This is used by the tests)"""
    if not send_new and filetype not in self._signature_help_available_requests:
      return False

    return self._signature_help_available_requests[ filetype ].Done()


  def SendSignatureHelpRequest( self ):
    """Send a signature help request, if we're ready to. Return whether or not a
    request was sent (and should be checked later)"""
    if not self.NativeFiletypeCompletionUsable():
      return False

    for filetype in vimsupport.CurrentFiletypes():
      if not self.SignatureHelpAvailableRequestComplete( filetype ):
        continue

      sig_help_available = self._signature_help_available_requests[
          filetype ].Response()
      if sig_help_available == 'NO':
        continue

      if sig_help_available == 'PENDING':
        # Send another /signature_help_available request
        self._signature_help_available_requests[ filetype ].Start( filetype )
        continue

      if not self._latest_completion_request:
        return False

      request_data = self._latest_completion_request.request_data.copy()
      request_data[ 'signature_help_state' ] = self._signature_help_state.state

      self._AddExtraConfDataIfNeeded( request_data )

      self._latest_signature_help_request = SignatureHelpRequest( request_data )
      self._latest_signature_help_request.Start()
      return True

    return False


  def SignatureHelpRequestReady( self ):
    return bool( self._latest_signature_help_request and
                 self._latest_signature_help_request.Done() )


  def GetSignatureHelpResponse( self ):
    return self._latest_signature_help_request.Response()


  def ClearSignatureHelp( self ):
    self.UpdateSignatureHelp( {} )
    if self._latest_signature_help_request:
      self._latest_signature_help_request.Reset()


  def UpdateSignatureHelp( self, signature_info ):
    self._signature_help_state = signature_help.UpdateSignatureHelp(
      self._signature_help_state,
      signature_info )


  def _GetCommandRequestArguments( self,
                                   arguments,
                                   has_range,
                                   start_line,
                                   end_line ):
    final_arguments = []
    for argument in arguments:
      # The ft= option which specifies the completer when running a command is
      # ignored because it has not been working for a long time. The option is
      # still parsed to not break users that rely on it.
      if argument.startswith( 'ft=' ):
        continue
      final_arguments.append( argument )

    extra_data = {
      'options': {
        'tab_size': vimsupport.GetIntValue( 'shiftwidth()' ),
        'insert_spaces': vimsupport.GetBoolValue( '&expandtab' )
      }
    }
    if has_range:
      extra_data.update( vimsupport.BuildRange( start_line, end_line ) )
    self._AddExtraConfDataIfNeeded( extra_data )

    return final_arguments, extra_data



  def SendCommandRequest( self,
                          arguments,
                          modifiers,
                          has_range,
                          start_line,
                          end_line ):
    final_arguments, extra_data = self._GetCommandRequestArguments(
      arguments,
      has_range,
      start_line,
      end_line )
    return SendCommandRequest( final_arguments,
                               modifiers,
                               self._user_options[ 'goto_buffer_command' ],
                               extra_data )


  def GetCommandResponse( self, arguments ):
    final_arguments, extra_data = self._GetCommandRequestArguments(
      arguments,
      False,
      0,
      0 )
    return GetCommandResponse( final_arguments, extra_data )



  def GetDefinedSubcommands( self ):
    subcommands = BaseRequest().PostDataToHandler( BuildRequestData(),
                                                   'defined_subcommands' )
    return subcommands if subcommands else []


  def GetCurrentCompletionRequest( self ):
    return self._latest_completion_request


  def GetOmniCompleter( self ):
    return self._omnicomp


  def FiletypeCompleterExistsForFiletype( self, filetype ):
    try:
      return self._available_completers[ filetype ]
    except KeyError:
      pass

    exists_completer = SendCompleterAvailableRequest( filetype )
    if exists_completer is None:
      return False

    self._available_completers[ filetype ] = exists_completer
    return exists_completer


  def NativeFiletypeCompletionAvailable( self ):
    return any( self.FiletypeCompleterExistsForFiletype( x ) for x in
                vimsupport.CurrentFiletypes() )


  def NativeFiletypeCompletionUsable( self ):
    disabled_filetypes = self._user_options[
      'filetype_specific_completion_to_disable' ]
    return ( vimsupport.CurrentFiletypesEnabled( disabled_filetypes ) and
             self.NativeFiletypeCompletionAvailable() )


  def NeedsReparse( self ):
    return self.CurrentBuffer().NeedsReparse()


  def UpdateWithNewDiagnosticsForFile( self, filepath, diagnostics ):
    if not self._user_options[ 'show_diagnostics_ui' ]:
      return

    bufnr = vimsupport.GetBufferNumberForFilename( filepath )
    if bufnr in self._buffers and vimsupport.BufferIsVisible( bufnr ):
      # Note: We only update location lists, etc. for visible buffers, because
      # otherwise we default to using the current location list and the results
      # are that non-visible buffer errors clobber visible ones.
      self._buffers[ bufnr ].UpdateWithNewDiagnostics( diagnostics )
    else:
      # The project contains errors in file "filepath", but that file is not
      # open in any buffer. This happens for Language Server Protocol-based
      # completers, as they return diagnostics for the entire "project"
      # asynchronously (rather than per-file in the response to the parse
      # request).
      #
      # There are a number of possible approaches for
      # this, but for now we simply ignore them. Other options include:
      # - Use the QuickFix list to report project errors?
      # - Use a special buffer for project errors
      # - Put them in the location list of whatever the "current" buffer is
      # - Store them in case the buffer is opened later
      # - add a :YcmProjectDiags command
      # - Add them to errror/warning _counts_ but not any actual location list
      #   or other
      # - etc.
      #
      # However, none of those options are great, and lead to their own
      # complexities. So for now, we just ignore these diagnostics for files not
      # open in any buffer.
      pass


  def OnPeriodicTick( self ):
    if not self.IsServerAlive():
      # Server has died. We'll reset when the server is started again.
      return False
    elif not self.IsServerReady():
      # Try again in a jiffy
      return True

    for w in vim.windows:
      for filetype in vimsupport.FiletypesForBuffer( w.buffer ):
        if filetype not in self._message_poll_requests:
          self._message_poll_requests[ filetype ] = MessagesPoll( w.buffer )

        # None means don't poll this filetype
        if ( self._message_poll_requests[ filetype ] and
             not self._message_poll_requests[ filetype ].Poll( self ) ):
          self._message_poll_requests[ filetype ] = None

    return any( self._message_poll_requests.values() )


  def OnFileReadyToParse( self ):
    if not self.IsServerAlive():
      self.NotifyUserIfServerCrashed()
      return

    if not self.IsServerReady():
      return

    extra_data = {}
    self._AddTagsFilesIfNeeded( extra_data )
    self._AddSyntaxDataIfNeeded( extra_data )
    self._AddExtraConfDataIfNeeded( extra_data )

    self.CurrentBuffer().SendParseRequest( extra_data )


  def OnFileSave( self, saved_buffer_number ):
    SendEventNotificationAsync( 'FileSave', saved_buffer_number )


  def OnBufferUnload( self, deleted_buffer_number ):
    SendEventNotificationAsync( 'BufferUnload', deleted_buffer_number )


  def UpdateMatches( self ):
    self.CurrentBuffer().UpdateMatches()


  def OnFileTypeSet( self ):
    buffer_number = vimsupport.GetCurrentBufferNumber()
    filetypes = vimsupport.CurrentFiletypes()
    self._buffers[ buffer_number ].UpdateFromFileTypes( filetypes )
    self.OnBufferVisit()


  def OnBufferVisit( self ):
    for filetype in vimsupport.CurrentFiletypes():
      # Send the signature help available request for these filetypes if we need
      # to (as a side effect of checking if it is complete)
      self.SignatureHelpAvailableRequestComplete( filetype, True )

    extra_data = {}
    self._AddUltiSnipsDataIfNeeded( extra_data )
    SendEventNotificationAsync( 'BufferVisit', extra_data = extra_data )


  def CurrentBuffer( self ):
    return self._buffers[ vimsupport.GetCurrentBufferNumber() ]


  def OnInsertLeave( self ):
    SendEventNotificationAsync( 'InsertLeave' )


  def OnCursorMoved( self ):
    self.CurrentBuffer().OnCursorMoved()


  def _CleanLogfile( self ):
    logging.shutdown()
    if not self._user_options[ 'keep_logfiles' ]:
      if self._client_logfile:
        utils.RemoveIfExists( self._client_logfile )


  def OnVimLeave( self ):
    self._ShutdownServer()
    self._CleanLogfile()


  def OnCurrentIdentifierFinished( self ):
    SendEventNotificationAsync( 'CurrentIdentifierFinished' )


  def OnCompleteDone( self ):
    completion_request = self.GetCurrentCompletionRequest()
    if completion_request and completion_request.Done(): # GetCompletionsUserMayHaveCompleted will block thread
      completion_request.OnCompleteDone(self._complete_really_done)

      r = self.GetCompletionsUserMayHaveCompleted()
      if r:
          #  self._logger.info("match: %s", r[0].get(u"word"))
          self._used_completions.update( r.get(u"word") )

    if not self._complete_really_done: return
    complete_done_actions = self.GetCompleteDoneHooks()
    for action in complete_done_actions:
      action()
    self._complete_really_done = False

  def _scoreValue(self, score, cur_time):
    if not score: return 0
    decend_factor = ( 60 / (60 + (cur_time - score['time'])) )
    return score['val'] * decend_factor

  def GetCompleteDoneHooks( self ):
    filetypes = vimsupport.CurrentFiletypes()
    filetypes.append("*")
    for key, value in self._complete_done_hooks.items():
      if key in filetypes:
        yield value


  # return the vim completed item
  def GetCompletionsUserMayHaveCompleted( self ):
    latest_completion_request = self.GetCurrentCompletionRequest()
    if latest_completion_request:
        return latest_completion_request.CompletedItem()
    return None

  def _OnCompleteDone_UltiSnip(self):
      if not vimsupport.VariableExists('*UltiSnips#ExpandSnippet'): return

      #  self._logger.info( " try match" )
      completion = self.GetCompletionsUserMayHaveCompleted()
      #  self._logger.info( "completions: %s", completions )
      if not completion: return

      extra_menu_info = completion.get(u"menu")
      if not (extra_menu_info and extra_menu_info.startswith(u"<snip>")):
          return

      vim.eval('UltiSnips#ExpandSnippet()')
      return True

  def _OnCompleteDone_Swift(self):
      if not vimsupport.VariableExists('*UltiSnips#Anon'): return

      completion = self.GetCompletionsUserMayHaveCompleted()
      if not completion: return

      extra = GetCompletionExtraData(completion)
      templ = extra and extra.get(u"template")
      if not templ: return
      text = completion.get(u"word")
      if not text: return

      count = [0]
      # closure_pat = re.compile(r"{parenGroup}(\s*->.*)".format(parenGroup=r"\(([^)]*)\)"))
      def replaceParam(match):
          count[0] += 1
          expand = match.group(1)
          text = expand.split('##')
          # example:
          # <#T##onSubscribe: RxSubscribeHandler##RxSubscribeHandler##(RxObserver) -> RxDisposableProtocol#>
          #  if "->" in text[-1] and text[-1][0] == '(':

          # don't expand closure when complete, expand it use filetype mapping
          # m = closure_pat.match(text[-1])
          # if m:
          #     count[0] += 2
          #     return u"${%d:{(${%d:%s})%s in${%d}}}"%(count[0] -2, count[0] -1, m.group(1), m.group(2), count[0])
          # else:
          t = text[-1]
          return u"${%d:%s}"%(count[0], t)

      templ, n = re.subn(r'<#(.+?)#>', replaceParam, templ)
      #  print ( "anon:", templ, text )
      if templ != text:
          if templ[0:2] == '?.' and templ[2] == text[0]:
              text = '.' + text
          #  print("expand: ", completion)
          vim.eval("UltiSnips#Anon('{}', '{}', '', 'i')".format(
              *map(vimsupport.EscapeForVim, (templ, text))))
          return True

  def _OnCompleteDone_Clang(self):
      if not vimsupport.VariableExists('*UltiSnips#Anon'): return

      completion = self.GetCompletionsUserMayHaveCompleted()
      if not completion: return

      extra = GetCompletionExtraData(completion)
      templ = extra and extra.get(u"template")
      if not templ: return
      text = completion.get(u"word")
      if not text: return

      count = [0]
      ocblockPattern = re.compile(r"(\^[^(]*\([^)]*\))")
      def replaceParam(match):
          count[0] += 1
          expand = match.group(1)
          m = ocblockPattern.search(expand)
          if m:
              count[0] += 1
              return u"${%d:%s\\{$%d\\}}"%(count[0] - 1, m.group(1), count[0])
          return u"${%d:%s}"%(count[0], match.group(1))
      templ, n = re.subn(r'<#(.+?)#>', replaceParam, templ)
      #  print ( "anon:", templ, text )
      if templ != text:
          vim.eval("UltiSnips#Anon('{}', '{}', '', 'i')".format(
              *map(vimsupport.EscapeForVim, (templ, text))))
          return True


  def GetErrorCount( self ):
    return self.CurrentBuffer().GetErrorCount()


  def GetWarningCount( self ):
    return self.CurrentBuffer().GetWarningCount()


  def _PopulateLocationListWithLatestDiagnostics( self ):
    return self.CurrentBuffer().PopulateLocationList()


  def FileParseRequestReady( self ):
    # Return True if server is not ready yet, to stop repeating check timer.
    return ( not self.IsServerReady() or
             self.CurrentBuffer().FileParseRequestReady() )


  def HandleFileParseRequest( self, block = False ):
    if not self.IsServerReady():
      return

    current_buffer = self.CurrentBuffer()
    # Order is important here:
    # FileParseRequestReady has a low cost, while
    # NativeFiletypeCompletionUsable is a blocking server request
    if ( not current_buffer.IsResponseHandled() and
         current_buffer.FileParseRequestReady( block ) and
         self.NativeFiletypeCompletionUsable() ):

      if self._user_options[ 'show_diagnostics_ui' ]:
        # Forcefuly update the location list, etc. from the parse request when
        # doing something like :YcmDiags
        current_buffer.UpdateDiagnostics( block )
      else:
        # If the user disabled diagnostics, we just want to check
        # the _latest_file_parse_request for any exception or UnknownExtraConf
        # response, to allow the server to raise configuration warnings, etc.
        # to the user. We ignore any other supplied data.
        current_buffer.GetResponse()

      # We set the file parse request as handled because we want to prevent
      # repeated issuing of the same warnings/errors/prompts. Setting this
      # makes IsRequestHandled return True until the next request is created.
      #
      # Note: it is the server's responsibility to determine the frequency of
      # error/warning/prompts when receiving a FileReadyToParse event, but
      # it is our responsibility to ensure that we only apply the
      # warning/error/prompt received once (for each event).
      current_buffer.MarkResponseHandled()


  def ShouldResendFileParseRequest( self ):
    return self.CurrentBuffer().ShouldResendParseRequest()


  def DebugInfo( self ):
    debug_info = ''
    if self._client_logfile:
      debug_info += 'Client logfile: {0}\n'.format( self._client_logfile )
    extra_data = {}
    self._AddExtraConfDataIfNeeded( extra_data )
    debug_info += FormatDebugInfoResponse( SendDebugInfoRequest( extra_data ) )
    debug_info += 'Server running at: {0}\n'.format(
      BaseRequest.server_location )
    if self._server_popen:
      debug_info += 'Server process ID: {0}\n'.format( self._server_popen.pid )
    if self._server_stdout and self._server_stderr:
      debug_info += ( 'Server logfiles:\n'
                      '  {0}\n'
                      '  {1}'.format( self._server_stdout,
                                      self._server_stderr ) )
    return debug_info


  def GetLogfiles( self ):
    logfiles_list = [ self._client_logfile,
                      self._server_stdout,
                      self._server_stderr ]

    extra_data = {}
    self._AddExtraConfDataIfNeeded( extra_data )
    debug_info = SendDebugInfoRequest( extra_data )
    if debug_info:
      completer = debug_info[ 'completer' ]
      if completer:
        for server in completer[ 'servers' ]:
          logfiles_list.extend( server[ 'logfiles' ] )

    logfiles = {}
    for logfile in logfiles_list:
      logfiles[ os.path.basename( logfile ) ] = logfile
    return logfiles


  def _OpenLogfile( self, size, mods, logfile ):
    # Open log files in a horizontal window with the same behavior as the
    # preview window (same height and winfixheight enabled). Automatically
    # watch for changes. Set the cursor position at the end of the file.
    if not size:
      size = vimsupport.GetIntValue( '&previewheight' )

    options = {
      'size': size,
      'fix': True,
      'focus': False,
      'watch': True,
      'position': 'end',
      'mods': mods
    }

    vimsupport.OpenFilename( logfile, options )


  def _CloseLogfile( self, logfile ):
    vimsupport.CloseBuffersForFilename( logfile )


  def ToggleLogs( self, size, mods, *filenames ):
    logfiles = self.GetLogfiles()
    if not filenames:
      sorted_logfiles = sorted( logfiles )
      try:
        logfile_index = vimsupport.SelectFromList(
          'Which logfile do you wish to open (or close if already open)?',
          sorted_logfiles )
      except RuntimeError as e:
        vimsupport.PostVimMessage( str( e ) )
        return

      logfile = logfiles[ sorted_logfiles[ logfile_index ] ]
      if not vimsupport.BufferIsVisibleForFilename( logfile ):
        self._OpenLogfile( size, mods, logfile )
      else:
        self._CloseLogfile( logfile )
      return

    for filename in set( filenames ):
      if filename not in logfiles:
        continue

      logfile = logfiles[ filename ]

      if not vimsupport.BufferIsVisibleForFilename( logfile ):
        self._OpenLogfile( size, mods, logfile )
        continue

      self._CloseLogfile( logfile )


  def ShowDetailedDiagnostic( self ):
    detailed_diagnostic = BaseRequest().PostDataToHandler(
        BuildRequestData(), 'detailed_diagnostic' )

    if detailed_diagnostic and 'message' in detailed_diagnostic:
      vimsupport.PostVimMessage( detailed_diagnostic[ 'message' ],
                                 warning = False )


  def ForceCompileAndDiagnostics( self ):
    if not self.NativeFiletypeCompletionUsable():
      vimsupport.PostVimMessage(
          'Native filetype completion not supported for current file, '
          'cannot force recompilation.', warning = False )
      return False
    vimsupport.PostVimMessage(
        'Forcing compilation, this will block Vim until done.',
        warning = False )
    self.OnFileReadyToParse()
    self.HandleFileParseRequest( block = True )
    vimsupport.PostVimMessage( 'Diagnostics refreshed', warning = False )
    return True


  def ShowDiagnostics( self ):
    if not self.ForceCompileAndDiagnostics():
      return

    if not self._PopulateLocationListWithLatestDiagnostics():
      vimsupport.PostVimMessage( 'No warnings or errors detected.',
                                 warning = False )
      return

    if self._user_options[ 'open_loclist_on_ycm_diags' ]:
      vimsupport.OpenLocationList( focus = True )


  def _AddSyntaxDataIfNeeded( self, extra_data ):
    if not self._user_options[ 'seed_identifiers_with_syntax' ]:
      return
    filetype = vimsupport.CurrentFiletypes()[ 0 ]
    if filetype in self._filetypes_with_keywords_loaded:
      return

    if self.IsServerReady():
      self._filetypes_with_keywords_loaded.add( filetype )
    extra_data[ 'syntax_keywords' ] = list(
       syntax_parse.SyntaxKeywordsForCurrentBuffer() )


  def _AddTagsFilesIfNeeded( self, extra_data ):
    def GetTagFiles():
      tag_files = vim.eval( 'tagfiles()' )
      return [ os.path.join( utils.GetCurrentDirectory(), tag_file )
               for tag_file in tag_files ]

    if not self._user_options[ 'collect_identifiers_from_tags_files' ]:
      return
    extra_data[ 'tag_files' ] = GetTagFiles()


  def _AddExtraConfDataIfNeeded( self, extra_data ):
    def BuildExtraConfData( extra_conf_vim_data ):
        return dict( ( key, vimsupport.VimExpressionToPythonType( expr ) )
                    for key, expr in
                    map(lambda i:
                            ( i[0], i[1] ) if isinstance( i, list ) else
                            ( i, i ),
                        extra_conf_vim_data ) )

    extra_conf_vim_data = self._user_options[ 'extra_conf_vim_data' ]
    if extra_conf_vim_data:
      extra_data[ 'extra_conf_data' ] = BuildExtraConfData(
        extra_conf_vim_data )


  def _AddUltiSnipsDataIfNeeded( self, extra_data ):
    # See :h UltiSnips#SnippetsInCurrentScope.
    try:
      vim.eval( 'UltiSnips#SnippetsInCurrentScope( 1 )' )
    except vim.error:
      return

    snippets = vimsupport.GetVariableValue( 'g:current_ulti_dict_info' )
    extra_data[ 'ultisnips_snippets' ] = [
      { 'trigger': trigger,
        'description': snippet[ 'description' ] }
      for trigger, snippet in snippets.items()
    ]


class SawCompletions(object):
    def __init__(self):
        self._pos = None
        self._saw = dict()

    def saw(self, request, response):
        """ return saw completions """
        d = request.request_data
        pos = (d['line_num'], response['completion_start_column'], d['filepath'])
        if pos != self._pos: return frozenset()
        offset = d['column_num'] - pos[1]
        # logging.getLogger( 'ycm' ).info("saw %d (%s)", d['column_num'], pos) # type: logging.Logger
        return frozenset( word for (word, word_offset) in self._saw.items() if abs(word_offset - offset) > 1 )

    def see(self, request, response):
        """ record saw completions """
        d = request.request_data
        pos = (d['line_num'], response['completion_start_column'], d['filepath'])
        if self._pos != pos:
            self._saw = dict()
            self._pos = pos;

        offset = d['column_num'] - pos[1]
        for i in response['completions'][:2]:
            self._saw.setdefault(i['word'], offset)
        # logging.getLogger( 'ycm' ).info("see %s", self._saw) # type: logging.Logger

class UsedCompletions(object):
    def __init__(self, path):
        """ create UsedCompletions database at path """
        #  path = ':memory:'
        import sqlite3
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
CREATE TABLE IF NOT EXISTS used_completions(
name TEXT PRIMARY KEY,
val  REAL,
time INTEGER
) """)

    def __del__(self):
        self.conn.close()
        self.conn = None

    def update(self, word):
        """ mark word was used and update it's score """
        if not word: return

        with self.conn:
            t = time()
            s = 100

            c = self.conn.cursor()
            c.execute(""" SELECT val, time FROM used_completions WHERE name = ?  """, (word,))
            r = c.fetchone()
            if r: s += self._scoreValue(r, t)

            #  logging.getLogger( 'ycm' ).info("update word with score(%d): %s", s, word) # type: logging.Logger
            c.execute(""" REPLACE INTO used_completions VALUES (?, ?, ?)""", (word, s, t))

    def _scoreValue(self, score, cur_time):
        if not score: return 0
        # score decend by times
        decend_factor = ( 60 / (60 + (cur_time - score['time'])) )
        return score['val'] * decend_factor

    def scoreFor(self, word, time):
        """ get score for word at specified time """

        c = self.conn.cursor()
        c.execute(""" SELECT val, time FROM used_completions WHERE name = ?  """, (word,))
        r = c.fetchone()
        return self._scoreValue(r, time)

    def scoresFor(self, words, time):
        """ get score for words at specified time """
        c = self.conn.cursor()
        s = """ SELECT name, val, time FROM used_completions WHERE name in ({}) """.format(','.join(['?'] * len(words)) )
        c.execute(s, words)
        return { r[0] : self._scoreValue(r, time) for r in c.fetchall() }

def GetCompletionExtraData(completion):
  # extra_data = completion.get(u"extra_data")
  # if extra_data: return extra_data

  extra_data = completion.get(u"user_data")
  if not extra_data: return None
  if isinstance(extra_data, str):
      extra_data = json.loads(extra_data)
  # completion[u"extra_data"] = extra_data
  return extra_data

