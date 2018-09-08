#!/usr/bin/env python

import optparse
import paramiko
import tempfile
import urllib2
import ssl
import httplib
import json
import os
import sys
import logging
import tarfile
import untangle
from multiprocessing import Pool

# This script syncs local changes made to APS application to remote hosts.
# It automatically finds APS package location and rewrites files.
# It doesn't create new files or directories.
# Its main use is to apply local JS changes to one or several remote hosts.
# Run as shown in the example below, then press Enter every time you want to sync files.
#
# Usage: python sync-aps-js.py \
#               --appmeta /home/anton/dev/osa/modules/platform/cells/js-ui/aps_init_wizard/application/src/APP-META.xml \
#               --hosts destinationpoamn-1d35078c5920.aqa.int.zone,sourcepoamn-1d35078c5920.aqa.int.zone
#

LOG_FORMAT = "%(levelname)s %(asctime)s %(message)s"
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger()

parser = optparse.OptionParser()
parser.add_option('--hosts', dest="hosts", type="string", help="Comma separated list of hosts to update")
parser.add_option('--appmeta', dest="appmeta", type="string", help="Full path to APP-META.xml in repository that contains changes")

app_update = "/tmp/app-update.tar"
std_login = 'root'
std_pass = '1q2w3e'

def copy_poa_certificate(host_name):
    transport = paramiko.Transport((host_name, 22))
    transport.connect(username=std_login, password=std_pass)
    sftp = paramiko.SFTPClient.from_transport(transport)
    temp_file_name = tempfile.mktemp('.pem')
    sftp.get('/usr/local/pem/APS/certificates/poa.pem', temp_file_name)
    return temp_file_name

class HTTPS_OPENER (urllib2.HTTPSHandler):
    def __init__(self, key, cert):
        context = ssl._create_unverified_context()
        urllib2.HTTPSHandler.__init__(self, context=context)
        self.cert = cert
    def https_open(self, req):
        return self.do_open(self.getConnection, req, context=self._context)
    def getConnection(self, host, context=None, timeout=300):
        return httplib.HTTPSConnection(host, cert_file=self.cert, context=context)

def get_aps_packages(host_name):
    cert_file = copy_poa_certificate( host_name)
    get_aps_packages_url = "https://%s:6308/aps/2/packages" % host_name
    opener = urllib2.build_opener(HTTPS_OPENER(cert_file, cert_file))
    response = opener.open(get_aps_packages_url).read()
    return json.loads(response)

def find_package_uid(host_name, app_name):
    packages = get_aps_packages(host_name)
    for package in packages:
        if package['name'] == app_name:
            package_uid = package['aps']['id']
            log.info("Package uuid %s found for app '%s' on host '%s'" % (package_uid, app_name, host_name))
            return package_uid
    raise Exception("Couldn't find a package for application with name '%s' on host '%s'" % (app_name, host_name))

def update_host(tar, host_to_package_id, host_name):
    log.info("Syncing to host %s" % host_name)
    package_id = host_to_package_id[host_name]
    transport = paramiko.Transport((host_name, 22))
    transport.connect(username=std_login, password=std_pass)
    sftp = paramiko.SFTPClient.from_transport(transport)
    log.info("Copying update '%s' to package '%s' on host '%s'" % (tar, package_id, host_name))
    sftp.put(tar, app_update)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host_name, 22, 'root', '1q2w3e')
    target = "/usr/local/pem/APS/packages/%s/" % package_id
    command = "tar -xvf %s -C %s" % (app_update, target)
    log.info("Updating package '%s' on host '%s' with command '%s'" % (package_id, host_name, command))
    ssh.exec_command(command)
    log.info("All done here!")

def update_hosts(app_name, source, host_to_package_id):
    log.info("Syncing to hosts %s" % hosts)
    tar = tarfile.open(app_update, "w")
    tar.add(source, ".")
    tar.close()
    pool = Pool(processes=10)
    asyncs = []
    for host in host_to_package_id:
        asyncs.append(pool.apply_async(update_host, (app_update, host_to_package_id, host)))
    for async in asyncs:
        async.wait(60)

def get_target_hosts(opts):
    if not opts.hosts:
        raise Exception("List of target hosts must be specified")
    return [host.strip() for host in opts.hosts.split(",")]

def get_app_sources_and_name(opts):
    if not opts.appmeta:
        raise Exception("Full path to application APP-META.xml file in repository containing changes must be specified")
    app_meta = untangle.parse(opts.appmeta)
    return (app_meta.application.name.cdata, opts.appmeta.replace("/APP-META.xml", ""))

if __name__ == "__main__":
    (opts, args) = parser.parse_args()
    app_name, app_sources = get_app_sources_and_name(opts)
    hosts = get_target_hosts(opts)
    host_to_package_id = {}
    for host in hosts:
        package_uid = find_package_uid(host, app_name)
        host_to_package_id[host] = package_uid
    while True:
        print "Press Enter to sync '%s' app to following hosts:\n%s" % (app_name, "\n".join(hosts))
        cmd = raw_input()
        if cmd == "quit":
            exit(0)
        update_hosts(app_name, app_sources, host_to_package_id)
        print "\n"
