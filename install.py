#!/usr/bin/env python

import os
import subprocess
import sys
import os.path as p
import glob

DIR_OF_THIS_SCRIPT = p.dirname( p.abspath( __file__ ) )
DIR_OF_OLD_LIBS = p.join( DIR_OF_THIS_SCRIPT, 'python' )


def Main():
  build_file = p.join( DIR_OF_THIS_SCRIPT, 'third_party', 'ycmd', 'build.py' )

  if not p.isfile( build_file ):
    sys.exit( 'File ' + build_file + ' does not exist; you probably forgot '
              'to run:\n\tgit submodule update --init --recursive\n\n' )

  python_binary = sys.executable
  try:
      subprocess.check_call( [ python_binary, build_file ] + sys.argv[1:] )
  except subprocess.CalledProcessError as e:
      print(e.cmd, e.args, e.output, e.stderr)
      raise e
  finally:
      pass

  # Remove old YCM libs if present so that YCM can start.
  old_libs = (
    glob.glob( p.join( DIR_OF_OLD_LIBS, '*ycm_core.*' ) ) +
    glob.glob( p.join( DIR_OF_OLD_LIBS, '*ycm_client_support.*' ) ) +
    glob.glob( p.join( DIR_OF_OLD_LIBS, '*clang*.*') ) )
  for lib in old_libs:
    os.remove( lib )

if __name__ == "__main__":
  Main()
