#!/usr/bin/env python2

import apt
import sys
from subprocess import Popen, PIPE
import imp

apt_strict = None
for path in ('./apt_strict.py', '/usr/share/apt_strict/apt_strict.py'):
    try:
        apt_strict = imp.load_source('apt_strict', path)
    except:
        pass
if apt_strict is None:
    print >> sys.stderr, 'Failed to load module apt_strict'
    sys.exit(1)

# Options
HELP_MESSAGE = 'Usage: %s install|install-only-new|resolve|resolve-only-new [apt-get options] pkg1=version1 pkg2 ...' % sys.argv[0]

if __name__ == '__main__':

    apt_strict.die = apt_strict.die_standalone

    # Parse command-line arguments
    if '--help' in sys.argv:
        print >> sys.stderr, HELP_MESSAGE
        sys.exit(0)

    if '--debug' in sys.argv:
        apt_strict.DEBUG = True
        sys.argv.remove('--debug')

    ACTION = sys.argv[1]
    if ACTION not in ('install', 'install-only-new', 'resolve', 'resolve-only-new'):
        print >> sys.stderr, HELP_MESSAGE
        apt_strict.die('Invalid argument %s' % ACTION)
    else:
        sys.argv.remove(ACTION)

    # packages = {'name': {'version': 'x', 'resolved': False}}
    packages = {}
    apt_get_options = ''

    del sys.argv[0]
    prev_opt = ''
    while len(sys.argv) != 0:
        i = sys.argv[0]

        # primitive filtration of dangerous typos - we are running as root
        for j in ';', '|', '&', '(', ')', '{', '}':
            if j in i:
                apt_strict.die('Incorrect argument: %s' % j)

        if i[0] == '-':
            apt_get_options += i + ' '
            sys.argv.remove(i)
        elif ( prev_opt == '-o' ) and ( i.find( 'Dpkg::Options::=' ) == 0 ):
            apt_get_options += i + ' '
            sys.argv.remove(i)
        elif '=' not in i:
            packages[i] = {'version': None, 'resolved': False}
            sys.argv.remove(i)
        else:
            packages[i.split('=')[0]] = {'version': i.split('=')[1], 'resolved': False}
            sys.argv.remove(i)

        prev_opt = i

    apt_strict.debug('Initilizing apt cache interface')
    cache = apt.cache.Cache()

    # Resolve dependencies and store in packages
    packages = apt_strict.resolve_all(cache, packages, ACTION)

    if ACTION in ('resolve', 'resolve-only-new'):
        print(apt_strict.print_apt_string(packages))
        sys.exit(0)
    else:
        cmd = 'apt-get ' + apt_get_options + 'install' + apt_strict.print_apt_string(packages)
        apt_strict.debug('command to run:\n' + cmd)
        proc = Popen(cmd, shell=True)
        sys.exit(proc.wait())
