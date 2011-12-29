import urllib2
import json
import sys
import os.path
import random
import string
import base64

# from <http://code.activestate.com/recipes/146306/>
def encode_multipart_formdata(fields, files):
    """
    fields is a sequence of (name, value) elements for regular form fields.
    files is a sequence of (name, filename, value) elements for data to be uploaded as files
    Return (content_type, body) ready for httplib.HTTP instance
    """
    BOUNDARY = '----------ThIs_Is_tHe_bouNdaRY_$'
    BOUNDARY += ''.join(random.choice(string.digits) for x in range(10))
    CRLF = '\r\n'
    L = []
    for (key, value) in fields:
        L.append('--' + BOUNDARY)
        L.append('Content-Disposition: form-data; name="%s"' % key)
        L.append('')
        L.append(str(value))
    for (key, filename, value) in files:
        L.append('--' + BOUNDARY)
        L.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
        L.append('Content-Type: application/octet-stream')
        L.append('')
        L.append(str(value))
    L.append('--' + BOUNDARY + '--')
    L.append('')
    body = CRLF.join(L)
    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
    return content_type, body

# takes kwargs: token username password user repo
# user, repo are required!
# either a valid username,password or a token are also required!
# returns url on success, None on error
def ghub_upload(src, dest=None, description=None, **kwargs):
    if not os.path.exists(src):
        return None
    
    filesize = os.path.getsize(src)
    try:
        file_data = open(src, 'rb').read()
    except OSError:
        return None
    if dest is None:
        dest = os.path.split(src)[1]
    
    data = {"name" : dest, "size" : filesize}
    if not description is None:
        data["description"] = description
    
    data = json.dumps(data)
    headers = {'Content-type' : 'application/json'}
    if 'token' in kwargs:
        headers['Authorization'] = 'token {token}'.format(**kwargs)
    else:
        headers['Authorization'] = "Basic " + base64.encodestring('{username}:{password}'.format(**kwargs)).replace('\n', '')
    url = "https://api.github.com/repos/{user}/{repo}/downloads".format(**kwargs)
    
    try:
        r = urllib2.Request(url, data, headers)
        response = json.load(urllib2.urlopen(r))
    except (urllib2.HTTPError, ValueError):
        return None
    
    try:
        upload_form = [
            ('key', response['path']),
            ('acl', response['acl']),
            ('success_action_status', 201),
            ('filename', response['name']),
            ('AWSAccessKeyId', response['accesskeyid']),
            ('Policy', response['policy']),
            ('Signature', response['signature']),
            ('Content-Type', response['mime_type']),
        ]
    except KeyError:
        return None
    
    upload_type, upload_form = encode_multipart_formdata(upload_form, [('file', dest, file_data)])
    
    try:
        r = urllib2.Request("https://github.s3.amazonaws.com/", upload_form)
        r.add_header('Content-type', upload_type)
        upload_response = urllib2.urlopen(r)
        upload_response.read()
    except urllib2.HTTPError:
        return None
    return response['url']

