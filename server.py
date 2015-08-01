# -*- coding: utf-8 -*-
"""
Simple service that allows reviewing or merging branches 
that passed tests on CircleCI via tapping on actionable 
notifications via Yo.
(Currently only for iOS)

You'll need:
* 
Free CI: https://circleci.com

"""
import os
import requests
import redis
import pickle
import urlparse
from flask import request
from flask import Flask


url = urlparse.urlparse(os.environ.get('REDISCLOUD_URL'))
redis = redis.Redis(host=url.hostname, port=url.port, password=url.password)
app = Flask(__name__)

debug = True

YO_USERNAME = os.environ.get('YO_USERNAME')
YO_API_TOKEN = os.environ.get('YO_API_TOKEN')
GITHUB_ACCESS_TOKEN = os.environ.get('GITHUB_ACCESS_TOKEN')


@app.route('/circleci', methods=['POST'])
def circleci():

    '''
    This is the webhook that CircleCI calls when a build is completed.
    In the circleci.yml there should be:

    notify:
      webhooks:
        - url: https://yourserver.com/circleci

    '''

    # CircleCI webhook payload sample: https://circleci.com/docs/api#build
    circleci_payload = request.get_json(force=True).get('payload')
    subject = circleci_payload.get('subject')
    status = u'👍' if circleci_payload.get('status') == "success" else u'👎'

    if debug:
        print circleci_payload

    text = subject[:25] + u'... ' + status
    compare_url = circleci_payload.get('compare')

    # Send a Yo notifying about the build
    response = requests.post('http://api.justyo.co/yo/',
                             json={"api_token": YO_API_TOKEN,
                                   "response_pair": "Review.Merge",
                                   "username": YO_USERNAME,
                                   "text": text,
                                   "left_link": compare_url})

    # Store the build payload in redis with the yo_id as the key
    # so we can get the inf o of the build when the reply comes in
    yo_id = response.json().get('yo_id')
    pickled_circleci_payload = pickle.dumps(circleci_payload)
    redis.set(yo_id, pickled_circleci_payload, 3600)
    if debug:
        print response, response.text

    return 'OK'


@app.route("/circleci/reply", methods=['POST'])
def circlecireply():

    payload = request.get_json(force=True)
    display_name = payload.get('display_name')
    reply_to_object = payload.get('reply_to')  # This is the Yo that was sent up there ^
    reply_object = payload.get('reply')
    reply_text = reply_object.get('text')

    if reply_text == 'Merge':

        # Get the original Yo id from the payload
        original_yo_id = reply_to_object.get('yo_id')

        # Get the CircleCI payload from redis
        circleci_payload = pickle.loads(redis.get(original_yo_id))

        # Prepare the request to GitHub to merge the new branch to master
        github_username = circleci_payload.get('username')
        reponame = circleci_payload.get('reponame')
        branch = circleci_payload.get('branch')

        params = {
            "base": "master",
            "head": branch,
            "commit_message": display_name + ' merged "' + branch + '" to "master" via Yo.'
        }
        url = 'http://api.github.com/repos/' + github_username + '/' + reponame + '/merges?access_token=' + GITHUB_ACCESS_TOKEN
        response = requests.post(url, params)
        if debug:
            print response, response.text

    return 'OK'


if __name__ == "__main__":
    app.debug = debug
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
