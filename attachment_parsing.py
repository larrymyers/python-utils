import os
import sys
import poplib
import email
import mimetypes

# setup the OptionParser to read in the settings file to use

from optparse import OptionParser

usage = """Usage: %prog -s server-name -u username -p password

Example: python attachment_parsing.py -s pop.gmail.com -u your-email@gmail.com -p your-password -d ~/Desktop --use-ssl
"""
parser = OptionParser(usage)
parser.add_option('-s', '--pop-server', dest='server', help="The POP3 server to connect to")
parser.add_option('-P', '--port', dest='port', type='int', default=110, help="The POP3 server port, defaults to 110")
parser.add_option('-u', '--username', dest='username', help="The username for the pop3 account")
parser.add_option('-p', '--password', dest='password', help="The password for the pop3 account")
parser.add_option('-d', '--save-dir', dest='store_image_path', help="The directory to store attachments")
parser.add_option('--use-ssl', dest='use_ssl', action='store_true', default=False, help="Use SSL to connect, defaults port to 995")

(options, args) = parser.parse_args()

if not options.server:
    parser.error("You must specify a server")

if not options.username:
    parser.error("You must specify a username")

if not options.password:
    parser.error("You must specify a password")

if not options.store_image_path:
    parser.error("You must specify a path to store attachments")

# locals

server = options.server
port = options.port
username = options.username
password = options.password
store_image_path = options.store_image_path
use_ssl = options.use_ssl

# get a connection to the pop3 server

conn = None

if use_ssl and port == 110:
    port = 995

print server, port, username, password, store_image_path, use_ssl

if port == 995 or use_ssl:
    conn = poplib.POP3_SSL(server, port)
else:
    conn = poplib.POP3(server, port)

conn.user(username)
conn.pass_(password)

# get list of all messages and interate over them

msg_list = conn.list()

print 'message list length = ' + str(len(msg_list))
print msg_list

for item in msg_list[1]:
    msg_num = item.split()[0]
    
    # get the message content and convert to email.Message object
    
    content = conn.retr(msg_num)
    msg = email.message_from_string("\n".join(content[1]))
    
    # print Subject of message if it exists
    if 'Subject' in msg.keys():
        print msg['Subject']
    
    # if it doesn't exist, create the directory to save to
    
    if not os.path.isdir(store_image_path):
        os.mkdir(store_image_path)
    
    # iterate over the parts of the Message to find the attachment
    
    for part in msg.walk():
        # multipart/* are just containers
        if part.get_content_maintype() == 'multipart':
            continue
        
        filename = part.get_filename()
        
        if not filename:
            continue
        
        filepath = store_image_path + '/' + filename
        data = part.get_payload(decode=True)
        
        # read the data in the attachment and write to file
        
        if data is not None:
            fp = open(filepath, 'wb')
            fp.write(data)
            fp.close()
        
    

# close connection

conn.quit()
