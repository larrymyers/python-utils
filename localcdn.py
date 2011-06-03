#!/usr/bin/env python

"""
This script dynamically combines js and css assets, and provides a webserver for live dev mode
development. For static builds it combines and compresses the bundles, creating a deploy directory
suitable for creating a tarball and placing on a CDN origin server.

For compression it depends on the yuicompressor, which the script will fetch if needed.

To run the dev server and generate the bundles dynamically:

./localcdn.py -c localcdn.conf

To generate the deploy folder, suitable for placing on a CDN origin server:

./localcdn.py -c localcdn.conf -g

Embedding as WSGI Middleware:



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
    
Which is accessible via these URLs:

http://localhost:3000/js/deps.js
http://localhost:3000/js/appbundle.js
http://localhost:3000/css/main.css
http://localhost:3000/images/foo.png

And generates this directory structure in 'deploy' mode:

cdn-deploy/
    js/
        deps.js
        appbundle.js
    css/
        main.css
    images/
        foo.png
"""

import os
import sys
import json
import mimetypes
import subprocess

from wsgiref.simple_server import make_server

from shutil import copy2
from fnmatch import fnmatch
from optparse import OptionParser

yuicompressor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'yuicompressor.jar')

def get_yuicompressor():
    subprocess.call(['wget','http://yui.zenfs.com/releases/yuicompressor/yuicompressor-2.4.6.zip'])
    subprocess.call(['unzip','yuicompressor-2.4.6.zip'])
    subprocess.call(['mv','yuicompressor-2.4.6/build/yuicompressor-2.4.6.jar', yuicompressor_path])
    subprocess.call(['rm','-rf','yuicompressor-2.4.6','yuicompressor-2.4.6.zip'])


def parse_conf(confpath):
    """
    Loads the json conf from the given path, and converts relative paths to absolute paths
    for the srcDir and deployDir values.
    """
    
    if isinstance(confpath, dict):
        return confpath
    
    fullpath = os.path.abspath(confpath)
    root = os.path.dirname(fullpath)
    
    conf = json.loads(open(fullpath).read())
    conf['srcDir'] = os.path.join(root, conf['srcDir'])
    conf['deployDir'] = os.path.join(root, conf['deployDir'])
    
    return conf

def is_bundle(conf, path):
    """
    Returns True if the url path represents a bundle in the given conf.
    
    
    
    """
    
    parts = path.split('/')
    
    if len(parts) < 3:
        return False
    
    asset_type = parts[1]
    bundle_name = parts[2]
    
    return asset_type in conf and bundle_name in conf[asset_type]

def is_bundle_file(conf, path):
    """Returns True if the file path, expected to be relative to the srcDir, is part of a bundle"""
    
    if path[0] == '/':
        path = path[1:]
    
    # walk the config, checking for a match
    for asset_type in ['js','css']:
        for bundle_name in conf[asset_type].iterkeys():
            for f in conf[asset_type][bundle_name]:
                if os.path.join(asset_type, f) == path:
                    return True
    
    return False

def get_bundle(conf, asset_type, bundle_name):
    """Combines all the resources that represents a bundle and returns them as a single string"""
    
    content_type = 'application/javascript'
    content = []
    
    if asset_type == 'css':
        content_type = 'text/css'
    
    for asset in conf[asset_type][bundle_name]:
        content.append(open(os.path.join(conf['srcDir'], asset_type, asset)).read())
    
    content = ''.join(content)
    
    return '200 OK', content_type, content


def compress_content(content_type, content):
    """Compresses a js or css string and returns the compressed string"""
    
    command = 'java -jar %s --type=%s' % (yuicompressor_path, content_type)
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


def deploy(conf):
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
        for bundle_name in conf[asset_type].iterkeys():
            code, content_type, content = get_bundle(conf, asset_type, bundle_name)
            compressed = compress_content(asset_type, content)
            
            f = open(os.path.join(deploydir, asset_type, bundle_name), 'w')
            f.write(compressed)
            f.close()
        
    
    # now walk the srcDir and copy everything else over that's not part of a bundle
    for (root, dirs, files) in os.walk(srcdir):        
        relpath = root[len(srcdir):]
        
        for f in files:
            # skip the localcdn files, just copy actual static assets
            if fnmatch(f, 'localcdn.py') or fnmatch(f, 'yuicompressor*.jar') or fnmatch(f, '*.conf'):
                continue
            
            # skip files that are part of a static asset bundle
            if is_bundle_file(conf, os.path.join(relpath, f)):
                continue
            
            # make an intermediate dirs needed before the copy
            if not os.path.isdir(deploydir + relpath):
                os.makedirs(deploydir + relpath)
            
            copy2(os.path.join(root, f), os.path.join(deploydir + relpath, f))


def start_server(conf, port):
    static_app = StaticAssetMiddleware(conf)
    httpd = make_server('', port, DynamicAssetMiddleware(conf, static_app))
    
    print "Server started - http://%s:%s/" % ('localhost', port)
    
    httpd.serve_forever()


class DynamicAssetMiddleware:
    def __init__(self, config, app=None):
        self.config = parse_conf(config)
        self.app = app
    
    def __call__(self, environ, start_response):
        
        if is_bundle(self.config, environ['PATH_INFO']):
            parts = environ['PATH_INFO'].split('/') # ex: /js/foo.js
            asset_type = parts[1]
            bundle_name = parts[2]
            
            code, content_type, content = get_bundle(self.config, asset_type, bundle_name)
            
            start_response(code, [('Content-Type', content_type), ('Content-Length', str(len(content)))])
            
            return [content]
        
        if not self.app:
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            
            return ["Does not exist: %s" % environ['PATH_INFO']]
        
        # if a wsgi middleware app was provided, delegate handling the request to it
        return self.app(environ, start_response)


class StaticAssetMiddleware:
    def __init__(self, config):
        self.config = parse_conf(config)
    
    def __call__(self, environ, start_response):
        code = '404 Not Found'
        content_type = 'text/plain'
        content = 'File Not Found'
        
        filepath = self.config['srcDir'] + environ['PATH_INFO']
        
        if os.path.isfile(filepath):
            code = '200 OK'
            content_type = mimetypes.guess_type(filepath)[0] or 'text/plain'
            content = open(filepath).read()
         
        start_response(code, [('Content-Type', content_type)])
        
        return [content]
    


parser = OptionParser("localcdn.py -c CONFIG_FILE [options]")
parser.add_option('-p', '--port', dest='port', type='int', default=3000, help='the port to run the dev server on [defaults to 3000]')
parser.add_option('-c', '--config', dest='config_file', help='the config file path that defines the js/css bundles [required]')
parser.add_option('-g', '--generate', action='store_true', dest='generate', help='generate the deploy package to place on a CDN')
parser.add_option('--minify', action='store_true', dest='minify', help='have the dev server minify the bundles, by default bundles are served unminified')
parser.add_option('--no-minify', action='store_false', dest='no_minify', help="don't minify the bundles when generating the deploy folder, by default bundles are minified")

if __name__ == '__main__':
    (options, args) = parser.parse_args()
    
    if not options.config_file:
        parser.error('No config file specified.')
    
    conf = parse_conf(options.config_file)
    
    if options.generate:
        if not os.path.exists(yuicompressor_path):
            get_yuicompressor()
        
        deploy(conf)
    else:
        start_server(conf, options.port)
    

