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
import subprocess

def IsHeaderFile( filename ):
  extension = os.path.splitext( filename )[ 1 ]
  return extension in [ '.h', '.hxx', '.hpp', '.hh' ]

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
    '-fobjc-arc',
    #'-fobjc-abi-version=2',
    #  '-fmodules',
    '-fpascal-strings',
    '-fstrict-aliasing',
    '-Wno-unused-parameter',
    ]
    final_flags = flags

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

def isProjectRoot(directory):
    return os.path.exists(os.path.join(directory, '.git'))

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


def readFileList(path):
    with open(path) as f:
        return f.read().splitlines()

fileListCache = {}
def filterSwiftArgs(items):
    """
    f: should return True to accept, return number to skip next number flags
    """
    it = iter(items)
    try:
      while True:
        arg = next(it)

        if arg in {"-primary-file", "-o", "-serialize-diagnostics-path", "-Xfrontend"}:
            next(it)
            continue
        if arg.startswith("-emit"):
            if arg.endswith("-path"): next(it)
            continue
        if arg in {"-frontend", "-c", "-pch-disable-validation", "-index-system-modules", "-serialize-debugging-options", "-enable-objc-interop"}:
            continue
        if arg == "-filelist": # sourcekit dont support filelist, unfold it
            filelist = next(it)
            files = fileListCache.get(filelist)
            if files is None:
                files = readFileList(filelist)
                fileListCache[filelist] = files
            for f in files: # type: str
                f = f.strip()
                if f: yield f
            continue
        yield arg
    except StopIteration as e:
        pass

def findSwiftModuleRoot(filename):
    """ return project root or None. if not found"""
    filename = os.path.abspath(filename)
    directory = os.path.dirname(filename)
    flagFile = None
    compileFile = None
    while directory and directory != '/':
        p = os.path.join(directory, ".swiftflags")
        if os.path.isfile(p):
            return (directory, p, compileFile) # prefer use swiftflags file as module root directory

        if compileFile is None:
            p = os.path.join(directory, ".compile")
            if os.path.isfile(p): compileFile = p

        if isProjectRoot(directory): break
        else: directory = os.path.dirname(directory)
    else:
        return (None, flagFile, compileFile)

    return (directory, flagFile, compileFile)

compileFileCache = {}
def CommandForSwiftInCompile(filename, compileFile):
    info = compileFileCache.get(compileFile)
    if info is None:
        info = {}
        compileFileCache[compileFile] = info # cache first to avoid re enter when error

        import json
        with open(compileFile) as f:
            m = json.load(f) # type: list
            info.update( (j, i['command'])
                for i in m if "files" in i and "command" in i
                for j in i['files']
            ) # swift module files
            info.update( (i["file"],i["command"]) # now not use other argument, like cd
                        for i in m
                        if "file" in i and "command" in i ) # single file command
    return info.get(filename, "")

def FlagsForSwift(filename, **kwargs):
    filename = os.path.abspath(filename)
    final_flags = []
    project_root, flagFile, compileFile = findSwiftModuleRoot(filename)
    print(f"xxxx {project_root}, {compileFile}")
    if compileFile:
        command = CommandForSwiftInCompile(filename, compileFile)
        print(f"command for {filename} is: {command}")
        if command:
            import shlex
            flags = shlex.split(command)[1:] # ignore executable
            final_flags = list(filterSwiftArgs(flags))

    if not final_flags and flagFile:
        headers, frameworks = findAllHeaderDirectory(project_root)
        for h in headers:
            final_flags += ['-Xcc', '-I' + h]
        for f in frameworks:
            final_flags.append( '-F' + f )
        swiftfiles = findAllSwiftFiles(project_root)
        final_flags += swiftfiles
        a = additionalSwiftFlags(flagFile)
        if a:
            a = list(filterSwiftArgs(a))
            final_flags += a
        else:
            final_flags += [
                '-sdk', '/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk/',
                '-target', 'x86_64-apple-ios8.0',
            ]
    if not final_flags:
        final_flags = [
            '-sdk', '/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk/',
            '-target', 'x86_64-apple-ios8.0',
        ]

    return {
        'flags': final_flags,
        'do_cache': True
    }


DIR_OF_THIS_SCRIPT = os.path.abspath( os.path.dirname( __file__ ) )
DIR_OF_THIRD_PARTY = os.path.join( DIR_OF_THIS_SCRIPT, 'third_party' )
DIR_OF_YCMD_THIRD_PARTY = os.path.join( DIR_OF_THIRD_PARTY,
                                        'ycmd', 'third_party' )


def GetStandardLibraryIndexInSysPath( sys_path ):
  for index, path in enumerate( sys_path ):
    if os.path.isfile( os.path.join( path, 'os.py' ) ):
      return index
  raise RuntimeError( 'Could not find standard library path in Python path.' )


def PythonSysPath( **kwargs ):
  sys_path = kwargs[ 'sys_path' ]

  for folder in os.listdir( DIR_OF_THIRD_PARTY ):
    sys_path.insert( 0, os.path.realpath( os.path.join( DIR_OF_THIRD_PARTY,
                                                        folder ) ) )

  for folder in os.listdir( DIR_OF_YCMD_THIRD_PARTY ):
    if folder == 'python-future':
      folder = os.path.join( folder, 'src' )
      sys_path.insert( GetStandardLibraryIndexInSysPath( sys_path ) + 1,
                       os.path.realpath( os.path.join( DIR_OF_YCMD_THIRD_PARTY,
                                                       folder ) ) )
      continue

    sys_path.insert( 0, os.path.realpath( os.path.join( DIR_OF_YCMD_THIRD_PARTY,
                                                        folder ) ) )

  return sys_path
