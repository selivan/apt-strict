#!/usr/bin/python
'''
---
module: apt_strict
short_description: apt wrapper - installs precise versions of exactly pointed dependencies: libxx=1.2.3
description:
  - apt wrapper - installs precise versions of exactly pointed dependencies: libxx=1.2.3. Options are like options for apt module.
options:
  name:
  state:
  default_release:
  install_recommends:
  force:
  dpkg_options:
'''

import apt
import sys
import os
import json
import shlex
from pprint import pformat
from subprocess import Popen, PIPE

# Options
LOOP_LIMIT = 10000
DEBUG = False

def die_standalone(msg, exit_code=1):
    print >> sys.stderr, 'ERROR: ' + msg
    sys.exit(exit_code)


def die_module(msg, exit_code=0):
    print json.dumps({
    "failed" : True,
    "msg": msg
    })
    sys.exit(exit_code)


die = die_module


def debug(message):
    if DEBUG:
        print >> sys.stderr, 'DEBUG: ' + message


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
    if ACTION != 'resolve':
        # Clear list from already installed packages without explicit versions
        tmp = {k:v for (k,v) in package_list.iteritems() if k in cache and ( cache[k].installed is None or v['version'] is not None ) }
        package_list = tmp
        debug('# packages after first cleanup: %d' % len(package_list))
        # Clear list from already installed packages with necessary version
        tmp = {k:v for (k,v) in package_list.iteritems() if k in cache and not ( cache[k].installed is not None and cache[k].installed.version == v['version'])}
        package_list = tmp
        debug('# packages after second cleanup: %d' % len(package_list))

    return package_list


if __name__ == '__main__':

    # Parse parameters
    args_file = sys.argv[1]
    args_data = file(args_file).read()
    arguments = shlex.split(args_data)
    params = {'name': None, 'state': 'present', 'install_recommends': True, 'force': False,
              'default_release': None,
              'dpkg_options': ('force-confdef', 'force-confold')}
    for arg in arguments:
        if arg.count("=") in (1, 2):
            chunks = arg.split("=")
            key = chunks[0]
            value = "=".join(chunks[1:])
            if key in ("name", "pkg", "package"):
                params["name"] = value
            elif key == "state":
                if value in ('latest', 'present'):
                    params[key] = value
                else:
                    die_module('Wrong state value %s' % value)
            elif key == 'default_release':
                params[key] = value
            elif key in ('install_recommends', 'install-recommends'):
                if value in ("yes", "on"):
                    params['install_recommends'] = True
                else:
                    params['install_recommends'] = False
            elif key == 'force':
                if value in ("yes", "on"):
                    params['force'] = True
                else:
                    params['force'] = False
            elif key == 'dpkg_options':
                params['dpkg_options'] = value.split(',')
        else:
            die_module('Invalid argument: %s' % arg)
    if params['name'] is None:
        die_module('name parameter should be set')

    # Parse parameters
    if '=' in params['name']:
        name, version = params['name'].split('=')
    else:
        name = params['name']
        version = None
    packages = {name: {'version': version, 'resolved': False}}

    apt_get_options = ['--yes']
    if params['default_release'] is not None:
        apt_get_options.append('--target-release %s' % params['default_release'])
    if not params['install_recommends']:
        apt_get_options.append('--no-install-recommends')
    if params['force']:
        apt_get_options.append('--force-yes')
    for i in params['dpkg_options']:
        apt_get_options.append('-o "Dpkg::Options::=--%s"' % i)

    if params['state'] == 'present':
        ACTION = 'install-only-new'
    elif params['state'] == 'latest':
        ACTION = 'install'

    # Initilize apt cache interface
    cache = apt.cache.Cache()

    # Resolve dependencies
    packages = resolve_all(cache, packages, ACTION)

    if len(packages) == 0:
        print json.dumps({'changed': False})
        sys.exit(0)

    # Create command line and run
    apt_get_options = ' '.join(apt_get_options)
    cmd = 'apt-get ' + apt_get_options + ' install ' + print_apt_string(packages)
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    proc = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    out, err = proc.communicate()

    if proc.returncode == 0:
        print json.dumps({'changed': True, 'command': cmd, 'stdout': out, 'stderr': err})
        sys.exit(0)
    else:
        print json.dumps({'failed': True, 'msg': 'apt-get returned non-zero exit code', 'command': cmd, 'stdout': out, 'stderr': err})
        sys.exit(0)
