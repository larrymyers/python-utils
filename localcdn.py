#!/usr/bin/env python

'''
This script dynamically combines js and css bundles, and provides a webserver for live dev mode
development. For static builds it combines and compresses the bundles, creating a deploy directory
suitable for creating a tarball and placing on a CDN origin server.

For compression it depends on the yuicompressor jar, which is expected to be in the same directory
as the script.

Usage:

./localcdn.py serve localcdn.conf
./localcdn.py deploy localcdn.conf

Config File Format:

{
    "srcDir": ".",
    "deployDir": "../cdn-deploy",
    "js": {
        "deps.js": [
            "ext/jquery-1.5.2.js",
            "ext/underscore.js",
            "ext/backbone.js"
        ],
        "appbundle.js": [
            "app.js",
            "model.js"
        ]
    },
    "css": {
        "main.css": ["screen.css", "widgets.css"]
    }
}

Which would correspond to the matching directory structure:

cdn/
    localcdn.conf
    js/
        ext/
            jquery-1.5.2.js
            underscore.js
            backbone.js
        app.js
        model.js
    css/
        screen.css
        widgets.css
    images/
        foo.png
    
Which in 'serve' mode would be accessible with these URLs:

http://localhost:3000/js/deps.js
http://localhost:3000/js/appbundle.js
http://localhost:3000/css/main.css
http://localhost:3000/images/foo.png

And generate this directory structure in 'deploy' mode:

cdn-deploy/
    js/
        deps.js
        appbundle.js
    css/
        main.css
    images/
        foo.png
'''

import os
import sys
import time
import json
from shutil import copy2
from fnmatch import fnmatch
import mimetypes
import subprocess
import BaseHTTPServer

conf = {}

def parse_conf(confpath):
    '''Loads the json conf from disk and converts relative paths to absolute paths'''
    
    fullpath = os.path.abspath(confpath)
    root = os.path.dirname(fullpath)
    
    global conf
    
    conf = json.loads(open(fullpath).read())
    conf['srcDir'] = os.path.join(root, conf['srcDir'])
    conf['deployDir'] = os.path.join(root, conf['deployDir'])


def is_bundle(asset_type, bundle_name):
    '''Returns true if the filename represents a bundle'''
    
    return asset_type in conf and bundle_name in conf[asset_type]


def get_bundle(asset_type, bundle_name):
    '''Combines all the resources that represents a bundle and returns them as a single string'''
    
    content = []
    
    for asset in conf[asset_type][bundle_name]:
        content.append(open(os.path.join(conf['srcDir'], asset_type, asset)).read())
    
    return ''.join(content)

def compress_content(content_type, content):
    '''Compresses a js or css string and returns the compressed version'''
    
    command = '%s --type=%s' % ('java -jar yuicompressor-2.4.6.jar', content_type)
    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    p.stdin.write(content)
    p.stdin.close()
    
    compressed = p.stdout.read()
    p.stdout.close()
    
    err = p.stderr.read()
    p.stderr.close()
    
    if p.wait() != 0:
        if not err:
            err = 'Unable to use YUI Compressor'
        
    
    return compressed


def deploy():
    srcdir = conf['srcDir']
    deploydir = conf['deployDir']
    jsdir = os.path.join(conf['deployDir'], 'js')
    cssdir = os.path.join(conf['deployDir'], 'css')
    
    if not os.path.isdir(deploydir):
        os.makedirs(deploydir)
    
    if not os.path.isdir(jsdir):
        os.mkdir(jsdir)
    
    if not os.path.isdir(cssdir):
        os.mkdir(cssdir)
    
    # generate all the bundles and write them to the deploy dir
    for asset_type in ['js','css']:
        for bundle in conf[asset_type].iterkeys():
            compressed = compress_content(asset_type, get_bundle(asset_type, bundle))
            
            f = open(os.path.join(deploydir, asset_type, bundle), 'w')
            f.write(compressed)
            f.close()
        
    
    # now walk the srcDir and copy everything else over that's not part of a bundle
    for (root, dirs, files) in os.walk(srcdir):        
        relpath = root[len(srcdir):]
        
        if not os.path.isdir(deploydir + relpath):
            os.makedirs(deploydir + relpath)
        
        for f in files:
            # skip the localcdn files, just copy actual static assets
            if fnmatch(f, 'localcdn.py') or fnmatch(f, 'yuicompressor*.jar') or fnmatch(f, '*.conf'):
                continue
            
            copy2(os.path.join(root, f), os.path.join(deploydir + relpath, f))
    


def start_server(port):
    httpd = BaseHTTPServer.HTTPServer(('', port), DynamicAssetHandler)
    
    print time.asctime(), "Server started - http://%s:%s/" % ('localhost', port)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    
    httpd.server_close()


class DynamicAssetHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
    
    def do_GET(self):
        content_type = mimetypes.guess_type(self.path)[0] or 'text/plain'
        content = ''
        
        parts = self.path.split('/')
        asset_type = parts[1]
        bundle_name = parts[2]
        
        if is_bundle(asset_type, bundle_name):
            content = get_bundle(asset_type, bundle_name)
        else:
            content = open(conf['srcDir'] + self.path).read()
        
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        
        self.wfile.write(content)
    


def help():
    print 'Usage: python localcdn <serve|deploy> <config-file> [port]'


if __name__ == '__main__':
    args = sys.argv
    
    if len(args) < 3:
        help()
        sys.exit()
    
    command = args[1].lower()
    confpath = args[2]
    port = 3000
    
    if len(args) > 3:
        port = int(args[3])
    
    parse_conf(confpath)
    
    if command == 'serve':
        start_server(port)
    elif command == 'deploy':
        deploy()
    else:
        help()
    

