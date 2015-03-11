#!/usr/bin/env python2

import apt
import sys
from pprint import pprint, pformat
import json
from subprocess import Popen


def die(message, exit_code=1):
    print >> sys.stderr, 'ERROR: ' + message
    sys.exit(exit_code)


def debug(message, common_message=None):
    if DEBUG:
        if common_message is None:
            print >> sys.stderr, 'DEBUG: ' + message
        else:
            common_message.append('DEBUG: ' + message)


def info(message, common_message=None):
    if common_message is None:
        print message
    else:
        common_message.append(message)


def print_apt_string(package_list):
    """ Return string to use with apt-get """
    result = ''
    for k,v in package_list.iteritems():
        if v['version'] is None or v['version'] == '':
            result += ' ' + k
        else:
            result += ' ' + k + '=' + v['version']
    return result


def print_ansible_apt_list(package_list):
    """ Return list to use with ansible apt module """
    result = []
    for k,v in package_list.iteritems():
        if v['version'] is None or v['version'] == '':
            result.append(k)
        else:
            result.append(k + '=' + v['version'])
    return result


def resolve_deps(package_name, package_list, cache):
    """Resolve package dependencies and add them to package_list
    package_name indicates entry in package_list"""
    debug('resolve_deps(%s)' % package_name)

    # Check correct call
    if package_list[package_name]['resolved']:
        debug('resolve_deps incorrect call: package %s already resolved' % package_name)
        return

    # Virtual package - do not mess with it, let apt think
    if package_name not in cache:
        providing = [ i.name for i in cache.get_providing_packages(package_name) ]
        if len(providing) == 0:
            die('error in resolve_deps: %s is virtual package and no one can provide it' % package_name)
        else:
            debug('virtual package %s - will not be checked futher' % package_name)
            package_list[package_name]['resolved'] = True
            return

    package_props = package_list[package_name]
    pkg = cache[package_name]

    # No version given - use candidate
    if package_props['version'] is None or package_props['version'] == '':
        ver = pkg.candidate
        debug('no explicit version required for %s - will use candidate version %s' % (package_name, ver.version))
    # Explicit version given - let's resolve it
    elif package_props['version'] in pkg.versions.keys():
        ver = pkg.versions[package_props['version']]
        debug('explicit version %s required for %s' % (ver.version, package_name))
    else:
        die('Version %s for package %s not found' % (package_props['version'], package_name))
        ver = None # never happens, just to supress PyCharm warning

    # Process dependencies
    for dep in ver.dependencies:

        dep_resolved = False

        # Check if any of variants already installed
        # If precise version required - handle it
        for bdep in dep.or_dependencies:

            # Save resolved state: prevent endless loop
            if bdep.name in package_list:
                bdep_resolved = package_list[bdep.name]['resolved']
            else:
                bdep_resolved = False

            # One of dependencies variant is installed
            if bdep.name in cache and cache[bdep.name].installed is not None:
                debug('already installed: %s' % bdep.name)
                # Found installed dependency for which we need precise version
                if bdep.relation == '=':
                    package_list[bdep.name] = {'version': bdep.version, 'resolved': bdep_resolved}
                    debug('added dependency with excplicit version: %s=%s' % (bdep.name, bdep.version))
                else:
                    # package_list[bdep.name] = {'version': None, 'resolved': bdep_resolved}
                    debug('found dependency without explicit version - do not add: %s' % bdep.name)
                dep_resolved = True
                break

        # No already installed variants found - get first
        # If precise version required - handle it
        if not dep_resolved:
            debug('not installed: %s' % bdep.name)
            bdep = dep.or_dependencies.pop()

            if bdep.name in package_list:
                bdep_resolved = package_list[bdep.name]['resolved']
            else:
                bdep_resolved = False

            if bdep.relation == '=':
                package_list[bdep.name] = {'version': bdep.version, 'resolved': bdep_resolved}
                debug('added dependency with excplicit version: %s=%s' % (bdep.name, bdep.version))
            else:
                # package_list[bdep.name] = {'version': None, 'resolved': bdep_resolved}
                debug('found dependency without explicit version - do not add: %s' % bdep.name)

    package_list[package_name]['resolved'] = True


def resolve_all(cache, package_list, ACTION):
    """Resolve dependencies for everything in packages"""

    orig_packages=package_list.copy()

    debug('orig_packages: ' + pformat(orig_packages))

    # Clean from already installed for 'install-only-new'
    # not in cache - for virtual packages
    if ACTION in ('install-only-new', 'resolve-only-new'):
        package_list = {k:v for k,v in orig_packages.iteritems() if k not in cache or cache[k].installed is None}

    # First cycle - resolve packages with explicit versions
    loop_counter = 0
    loop_finished = False
    while not loop_finished:
        loop_finished = True
        for name, props in package_list.iteritems():
            if props['resolved'] is False and props['version'] is not None and props['version'] != '':
                loop_finished = False
                break # for
        if not loop_finished:
            resolve_deps(name, package_list, cache)

        loop_counter += 1
        if loop_counter > LOOP_LIMIT:
            die('Failed(1) to resolve dependencies in %d loops' % LOOP_LIMIT)

    # Second cycle - resolve packages without explicit versions
    loop_counter = 0
    loop_finished = False
    while not loop_finished:
        loop_finished = True
        for name, props in package_list.iteritems():
            if props['resolved'] is False and (props['version'] is None or props['version'] != ''):
                loop_finished = False
                break # for
        if not loop_finished:
            resolve_deps(name, package_list, cache)

        loop_counter += 1
        if loop_counter > LOOP_LIMIT:
            die('Failed(2) to resolve dependencies in %d loops' % LOOP_LIMIT)

    debug('# packages resolved: %d' % len(package_list))
    # Clear list from already installed packages without explicit versions
    tmp = {k:v for (k,v) in package_list.iteritems() if k in cache and ( cache[k].installed is None or v['version'] is not None ) }
    package_list = tmp
    debug('# packages after first cleanup: %d' % len(package_list))
    # Clear list from already installed packages with necessary version
    tmp = {k:v for (k,v) in package_list.iteritems() if k in cache and not ( cache[k].installed is not None and cache[k].installed.version == v['version'])}
    package_list = tmp
    debug('# packages after second cleanup: %d' % len(package_list))

    # debug('resolve_all() result: \n' + pformat(package_list))
    return package_list


if __name__ == '__main__':

    # Options
    LOOP_LIMIT = 10000
    DEBUG = False
    HELP_MESSAGE = 'Usage: %s install|install-only-new|resolve|resolve-only-new [apt-get options] pkg1=version1 pkg2 ...' % sys.argv[0]

    # Parse command-line arguments
    if '--help' in sys.argv:
        print >> sys.stderr, HELP_MESSAGE
        sys.exit(0)

    if '--debug' in sys.argv:
        DEBUG = True
        sys.argv.remove('--debug')

    ACTION = sys.argv[1]
    if ACTION not in ('install', 'install-only-new', 'resolve', 'resolve-only-new'):
        print >> sys.stderr, HELP_MESSAGE
        die('Invalid argument %s')
    else:
        sys.argv.remove(ACTION)

    # packages = {'name': {'version': 'x', 'resolved': False}}
    packages = {}
    apt_get_options = ''

    del sys.argv[0]
    while len(sys.argv) != 0:
        i = sys.argv[0]

        # primitive filtration of dangerous typos - we are running as root
        for j in ';', '|', '&', '(', ')', '{', '}':
            if j in i:
                die('Incorrect argument: %s' % j)

        if i[0] == '-':
            apt_get_options += i + ' '
            sys.argv.remove(i)
        elif '=' not in i:
            packages[i] = {'version': None, 'resolved': False}
            sys.argv.remove(i)
        else:
            packages[i.split('=')[0]] = {'version': i.split('=')[1], 'resolved': False}
            sys.argv.remove(i)

    debug('Initilizing apt cache interface')
    cache = apt.cache.Cache()

    # Resolve dependencies and store in packages
    packages = resolve_all(cache, packages, ACTION)

    if ACTION in ('resolve', 'resolve-only-new'):
        info(print_apt_string(packages))
        sys.exit(0)
    else:
        cmd = 'apt-get ' + apt_get_options + 'install' + print_apt_string(packages)
        debug('command to run:\n' + cmd)
        proc = Popen(cmd, shell=True)
        sys.exit(proc.wait())
