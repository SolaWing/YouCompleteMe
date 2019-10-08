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
import re

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

        p = os.path.join(directory, ".flags")
        if os.path.isfile(p):
            return (directory, pchFile, p) # prefer use swiftflags file as module root directory
        if isProjectRoot(directory):
            return (directory, pchFile, None)
        else:
            directory = os.path.dirname(directory)
    else:
        return (None, None, None)

def filterCArgs(items):
    """
    f: should return True to accept, return number to skip next number flags
    """
    it = iter(items)
    try:
      while True:
        arg = next(it)

        if arg in {"-o", "-c",  "-x", "--serialize-diagnostics"}:
            next(it)
            continue
        if arg == "-fmodules": continue # YCM bugs, not support modules
        if arg.startswith("-std"): continue # skip for custom set
        if arg.startswith("-emit"):
            if arg.endswith("-path"): next(it)
            continue
        yield arg
    except StopIteration as e:
        pass

def FlagsForFile( filename, **kwargs ):
    final_flags = []

    # find all headers in file project
    project_root, pchFile, flagFile = findProjectRootAndPchFile(filename)
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
            a = additionalFlags(flagFile)
            if a: final_flags += (arg for arg in filterCArgs(a))
        except Exception as e:
            import logging
            logging.exception('headers append fail!')

    if any(filename.endswith(ext) for ext in ('.m', '.c', '.h')):
        final_flags.extend(['-std=gnu11', '-x', 'objective-c'])
    else:
        final_flags.extend(['-std=gnu++14', '-x', 'objective-c++'])
    try:
        final_flags += kwargs['client_data']['ycm_additional_flags']
    except Exception as e:
        pass

    return {
        'flags': final_flags,
        'do_cache': True
    }

def isProjectRoot(directory):
    return os.path.exists(os.path.join(directory, '.git'))

def additionalFlags(flagsPath):
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
    return [os.path.realpath(l) for l in output.splitlines()]


cmd_split_pattern = re.compile(r"""
"([^"]*)" |     # like "xxx xxx"
'([^']*)' |     # like 'xxx xxx'
((?:\\[ ]|\S)+) # like xxx\ xxx
""", re.X)
def cmd_split(s):
    # shlex.split is slow, use a simple version, only consider most case
    def extract(m):
        if m.lastindex == 3: # \ escape version. remove it
            return m.group(m.lastindex).replace("\\ ", " ")
        return m.group(m.lastindex)
    return [extract(m)
            for m in cmd_split_pattern.finditer(s)]

def readFileList(path):
    with open(path) as f:
        return cmd_split(f.read())

def getFileList(path, cache):
    files = cache.get(path)
    if files is None:
        files = readFileList(path)
        cache[path] = files
    return files

def filterSwiftArgs(items, fileListCache):
    """
    f: should return True to accept, return number to skip next number flags
    """
    it = iter(items)
    try:
      while True:
        arg = next(it)

        if arg in {"-primary-file", "-o", "-serialize-diagnostics-path"}:
            next(it)
            continue
        if arg.startswith("-emit"):
            if arg.endswith("-path"): next(it)
            continue
        if arg in {"-frontend", "-c", "-pch-disable-validation", "-index-system-modules", "-serialize-debugging-options", "-enable-objc-interop"}:
            continue
        if arg == "-filelist": # sourcekit dont support filelist, unfold it
            yield from getFileList(next(it), fileListCache)
            continue
        if arg.startswith("@"): # swift 5.1 filelist, unfold it
            yield from getFileList(arg[1:], fileListCache)
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

def CommandForSwiftInCompile(filename, compileFile, global_store):
    store = global_store.setdefault('compile', {})
    info = store.get(compileFile)
    if info is None:
        info = {}
        store[compileFile] = info # cache first to avoid re enter when error

        import json
        with open(compileFile) as f:
            m = json.load(f) # type: list
            info.update( (f, i['command'])
                for i in m if "files" in i and "command" in i
                for f in i['files']
            ) # swift module files
            info.update( (f.strip(), i['command'])
                for i in m if "fileLists" in i and "command" in i
                for l in i['fileLists'] if os.path.isfile(l)
                for f in getFileList(l, global_store.setdefault('filelist', {}))
            ) # swift file lists
            info.update( (i["file"],i["command"]) # now not use other argument, like cd
                        for i in m
                        if "file" in i and "command" in i ) # single file command
    return info.get(filename, "")

globalStore = {}
def FlagsForSwift(filename, **kwargs):
    store = kwargs.get('store', globalStore)
    print("store is ", store)
    filename = os.path.realpath(filename)
    final_flags = []
    project_root, flagFile, compileFile = findSwiftModuleRoot(filename)
    print(f"root: {project_root}, {compileFile}")
    if compileFile:
        command = CommandForSwiftInCompile(filename, compileFile, store)
        print(f"command for {filename} is: {command}")
        if command:
            import shlex
            flags = shlex.split(command)[1:] # ignore executable
            final_flags = list(filterSwiftArgs(flags, store.setdefault('filelist', {})))

    if not final_flags and flagFile:
        headers, frameworks = findAllHeaderDirectory(project_root)
        for h in headers:
            final_flags += ['-Xcc', '-I' + h]
        for f in frameworks:
            final_flags.append( '-F' + f )
        swiftfiles = findAllSwiftFiles(project_root)
        final_flags += swiftfiles
        a = additionalFlags(flagFile)
        if a:
            # sourcekit not allow same swift name. so if same name, use the find one to support move file
            swift_names = set( os.path.basename(p) for p in swiftfiles )
            final_flags += (arg for arg in filterSwiftArgs(a, store.setdefault('filelist', {}))
                                if os.path.basename(arg) not in swift_names)
        else:
            final_flags += [
                '-sdk', '/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/',
            ]
    if not final_flags:
        final_flags = [
            filename,
            '-sdk', '/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/',
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
