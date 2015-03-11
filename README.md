## apt-strict

apt-get wrapper to install precise versions of exactly pointed dependencies: libxx=1.2.3.

Against expectations, apt-get in this case installs most recent avaliable version of libxx. Sometimes this is not desirable. For example, if you distribute your software to servers with packages, and can not split testing/stable package versions by different repositories.

Usage: `apt-strict install|install-only-new|resolve|resolve-only-new --any-apt-get-options package1 package2=version`

All apt-get options are supported, also it has `--help` and `--debug`. 

Bash completion included.

## Ansible module
```yaml
 - apt_strict: name=foo state=present
```

Options have same meaning as in apt module:

 - name
 - state: present(default)|latest
 - default_release
 - install_recommends
 - force
 - dpkg_options


## Links

http://apt.alioth.debian.org/python-apt-doc/

http://fahdshariff.blogspot.ru/2011/04/writing-your-own-bash-completion.html

http://docs.ansible.com/developing_modules.html
