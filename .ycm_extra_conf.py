# flake8: noqa
# This file is NOT licensed under the GPLv3, which is the license for the rest
# of YouCompleteMe.
#
# Here's the license text for this file:
#
# This is free and unencumbered software released into the public domain.
#
# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.
#
# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# For more information, please refer to <http://unlicense.org/>

import os
import ycm_core
import subprocess

# These are the compilation flags that will be used in case there's no
# compilation database set (by default, one is not set).
# CHANGE THIS LIST OF FLAGS. YES, THIS IS THE DROID YOU HAVE BEEN LOOKING FOR.

src = os.path.dirname( os.path.abspath( __file__ ) )

flags = [
'-Wall',
'-Wextra',
##'-Wc++98-compat',
'-Wno-long-long',
'-Wno-variadic-macros',
'-Wno-nullability-completeness',
'-fexceptions',
##'-DNDEBUG',
##'-DNS_BLOCK_ASSERTIONS=1',
'-DDEBUG=1',
## THIS IS IMPORTANT! Without a "-std=<something>" flag, clang won't know which
## language to use when compiling headers. So it will guess. Badly. So C++
## headers will be compiled as C headers. You don't want that so ALWAYS specify
## a "-std=<something>".
## For a C project, you would set this to something like 'c99' instead of
## 'c++11'.
#'-std=gnu11',
'-D__arm__',
'-D__OBJC__=1',
'-arch arm64',
'-miphoneos-version-min=8.0',
# ...and the same thing goes for the magic -x option which specifies the
# language that the files to be compiled are written in. This is mostly
# relevant for c++ headers.
# For a C project, you would set this to 'c' instead of 'c++'.
'-x',
'objective-c++',
'-isystem','/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk/usr/include',
'-iframework/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk/System/Library/Frameworks',
'-iframework/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/Library/Frameworks',
'-isystem',
'/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/c++/v1',
'-isystem',
'/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/include',
#  '-isystem', os.path.join( src, "third_party/ycmd/clang_includes/include" ),
#'-I%s'%src,
#'-ObjC++',
'-fobjc-arc',
#'-fmessage-length=0',
#'-Os',
#'-fobjc-abi-version=2',
#  '-fmodules',
'-fpascal-strings',
'-fstrict-aliasing',
#warnings
#'-Wno-trigraphs',
#'-Wno-missing-field-initializers',
#'-Wno-missing-prototypes',
#'-Werror=return-type',
#'-Wno-implicit-atomic-properties',
#'-Werror=deprecated-objc-isa-usage',
#'-Werror=objc-root-class',
#'-Wno-receiver-is-weak',
#'-Wno-arc-repeated-use-of-weak',
#'-Wduplicate-method-match',
#'-Wno-missing-braces',
#'-Wparentheses',
#'-Wswitch',
#'-Wunused-function',
#'-Wno-unused-label',
'-Wno-unused-parameter',
#'-Wunused-variable',
#'-Wunused-value',
#'-Wempty-body',
#'-Wconditional-uninitialized',
#'-Wno-unknown-pragmas',
#'-Wno-shadow',
#'-Wno-four-char-constants',
#'-Wno-conversion',
#'-Wconstant-conversion',
#'-Wint-conversion',
#'-Wbool-conversion',
#'-Wenum-conversion',
#'-Wshorten-64-to-32',
#'-Wpointer-sign',
#'-Wno-newline-eof',
#'-Wno-selector',
#'-Wno-strict-selector-match',
#'-Wundeclared-selector',
#'-Wno-deprecated-implementations',
#'-Wprotocol',
#'-Wdeprecated-declarations',
#'-Wno-sign-conversion',
]


# Set this to the absolute path to the folder (NOT the file!) containing the
# compile_commands.json file to use that instead of 'flags'. See here for
# more details: http://clang.llvm.org/docs/JSONCompilationDatabase.html
#
# Most projects will NOT need to set this to anything; you can just change the
# 'flags' list of compilation flags. Notice that YCM itself uses that approach.
compilation_database_folder = ''
#compilation_database_folder = ''

if os.path.exists( compilation_database_folder ):
  database = ycm_core.CompilationDatabase( compilation_database_folder )
else:
  database = None

SOURCE_EXTENSIONS = [ '.cpp', '.cxx', '.cc', '.c', '.m', '.mm' ]

def DirectoryOfThisScript():
  return os.path.dirname( os.path.abspath( __file__ ) )


def MakeRelativePathsInFlagsAbsolute( flags, working_directory ):
  if not working_directory:
    return list( flags )
  new_flags = []
  make_next_absolute = False
  path_flags = [ '-isystem', '-I', '-iquote', '--sysroot=' ]
  for flag in flags:
    new_flag = flag

    if make_next_absolute:
      make_next_absolute = False
      if not flag.startswith( '/' ):
        new_flag = os.path.join( working_directory, flag )

    for path_flag in path_flags:
      if flag == path_flag:
        make_next_absolute = True
        break

      if flag.startswith( path_flag ):
        path = flag[ len( path_flag ): ]
        new_flag = path_flag + os.path.join( working_directory, path )
        break

    if new_flag:
      new_flags.append( new_flag )
  return new_flags


def IsHeaderFile( filename ):
  extension = os.path.splitext( filename )[ 1 ]
  return extension in [ '.h', '.hxx', '.hpp', '.hh' ]

def isProjectRoot(directory):
    return os.path.exists(os.path.join(directory, '.git'))

def fileInDir(directory, contains):
    for f in os.listdir(directory):
        if contains(f): return os.path.join(directory, f)

    return None

def pchFileInDir(directory):
    return fileInDir(directory, lambda f: f.endswith('.pch'))

def findProjectRootAndPchFile(filename):
    """ return project root or None. if not found"""
    filename = os.path.abspath(filename)
    directory = os.path.dirname(filename)
    pchFile = None
    while directory and directory != '/':
        # try to find a pchFile in parent directory
        if pchFile is None: pchFile = pchFileInDir(directory)
        if isProjectRoot(directory): break
        else: directory = os.path.dirname(directory)
    else:
        return (None, None)

    return (directory, pchFile)

def additionalFlags(root):
    flagsPath = os.path.join(root, '.flags')
    if os.path.isfile(flagsPath):
        with open(flagsPath) as f:
            return list(filter( bool, (line.strip() for line in f) ))
    return []

def additionalSwiftFlags(flagsPath):
    # flagsPath = os.path.join(root, '.swiftflags')
    if flagsPath and os.path.isfile(flagsPath):
        def valid(s):
            return s and not s.startswith('#')
        with open(flagsPath) as f:
            return list(filter( valid, (line.strip() for line in f) ))
    return []

headerDirsCacheDict = dict()
def findAllHeaderDirectory(rootDirectory):
    headerDirs = headerDirsCacheDict.get(rootDirectory)
    if headerDirs:
        return headerDirs

    output = subprocess.check_output(['find', '-L', rootDirectory, '-name', '*.h'],
                                     universal_newlines=True)
    headers = output.splitlines()
    headerDirs = set()
    frameworks = set()
    for h in headers:
        frameworkIndex = h.rfind('.framework')
        if frameworkIndex != -1:
            h = os.path.dirname(h[:frameworkIndex])
            frameworks.add(h)
        else:
            h = os.path.dirname(h)
            headerDirs.add(h)
            # contains more one dir for import with module name
            # don't contains more one module name dir. if need, can specify in .flags
            # conflict with #if_include framework check
            #  h = os.path.dirname(h)
            #  headerDirs.add(h)

    headerDirsCacheDict[rootDirectory] = (headerDirs, frameworks)
    return headerDirs, frameworks

def findAllSwiftFiles(rootDirectory):
    output = subprocess.check_output(['find', '-H', rootDirectory, '-name', '*.swift'],
                                     universal_newlines=True)
    return output.splitlines()

def GetCompilationInfoForFile( filename ):
  # The compilation_commands.json file generated by CMake does not have entries
  # for header files. So we do our best by asking the db for flags for a
  # corresponding source file, if any. If one exists, the flags for that file
  # should be good enough.
  if IsHeaderFile( filename ):
    basename = os.path.splitext( filename )[ 0 ]
    for extension in SOURCE_EXTENSIONS:
      replacement_file = basename + extension
      if os.path.exists( replacement_file ):
        compilation_info = database.GetCompilationInfoForFile(
          replacement_file )
        if compilation_info.compiler_flags_:
          return compilation_info
    return None
  return database.GetCompilationInfoForFile( filename )

def escapeSpace( s ):
    return s.replace(' ', r'\ ')

def FlagsForFile( filename, **kwargs ):
  if database:
    # Bear in mind that compilation_info.compiler_flags_ does NOT return a
    # python list, but a "list-like" StringVec object
    compilation_info = GetCompilationInfoForFile( filename )
    if not compilation_info:
      return None

    final_flags = MakeRelativePathsInFlagsAbsolute(
      compilation_info.compiler_flags_,
      compilation_info.compiler_working_dir_ )

    # NOTE: This is just for YouCompleteMe; it's highly likely that your project
    # does NOT need to remove the stdlib flag. DO NOT USE THIS IN YOUR
    # ycm_extra_conf IF YOU'RE NOT 100% SURE YOU NEED IT.
    try:
      final_flags.remove( '-stdlib=libc++' )
    except ValueError:
      pass
  else:
   #  with open("/tmp/flags", "a") as out:
    # relative_to = DirectoryOfThisScript()
    # final_flags = MakeRelativePathsInFlagsAbsolute( flags, relative_to )
    final_flags = flags[:] #!! final_flags = []

    # find all headers in file project
    project_root, pchFile = findProjectRootAndPchFile(filename)
    #  print(project_root, pchFile, file=out)
    if project_root:
        try:
            headers, frameworks = findAllHeaderDirectory(project_root)
            #  print("header&framework:\n",headers, frameworks, file=out)
            if headers:
                final_flags += ['-I'+ s for s in headers]
            if frameworks:
                final_flags += ['-iframework'+s for s in frameworks]
            if pchFile:
                final_flags.append('-include'+pchFile)
        except Exception as e:
            import logging
            logging.exception('headers append fail!')
        final_flags += additionalFlags(project_root)

    if filename.endswith('.m') or filename.endswith('.c'):
        final_flags.append('-std=gnu11');
    else:
        final_flags.append('-std=gnu++14');

    try:
        final_flags += kwargs['client_data']['ycm_additional_flags']
    except Exception as e:
        pass

    #  print("final_flags:\n", final_flags, file=out)

  return {
    'flags': final_flags,
    'do_cache': True
  }

def findSwiftModuleRoot(filename):
    """ return project root or None. if not found"""
    filename = os.path.abspath(filename)
    directory = os.path.dirname(filename)
    flagFile = None
    while directory and directory != '/':
        # try to find a flagFile in parent directory
        # if flagFile is None:
        p = os.path.join(directory, ".swiftflags")
        if os.path.isfile(p):
            return (directory, p) # use swiftflags file as module root directory

        if isProjectRoot(directory): break
        else: directory = os.path.dirname(directory)
    else:
        return (None, None)

    return (directory, flagFile)

def FlagsForSwift(filename, **kwargs):
    final_flags = []
    project_root, flagFile = findSwiftModuleRoot(filename)
    if project_root:
        headers, frameworks = findAllHeaderDirectory(project_root)
        for h in headers:
            final_flags += ['-Xcc', '-I' + h]
        for f in frameworks:
            final_flags.append( '-F' + f )
        swiftfiles = findAllSwiftFiles(project_root)
        swiftfiles.remove(os.path.abspath(filename))
        final_flags += swiftfiles
        a = additionalSwiftFlags(flagFile)
        if a: final_flags += a
        else:
            final_flags += [
                '-sdk', '/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk/',
                '-target', 'x86_64-apple-ios8.0',
            ]
    else:
        final_flags += [
            '-sdk', '/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk/',
            '-target', 'x86_64-apple-ios8.0',
        ]


    # return { 'flags': final_flags }
    return {
        'flags': final_flags,
        'do_cache': True
    }
