import argparse
import codecs
import datetime
import json
import os
import sys
import time
import subprocess

from dotenv import load_dotenv
from xml.dom.minidom import parseString
import urllib as urllib
import send_telegram
import time

try:
	from instagram_private_api import (
		Client, ClientError, ClientLoginError,
		ClientCookieExpiredError, ClientLoginRequiredError,
		__version__ as client_version)
except ImportError:
	import sys

	sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
	from instagram_private_api import (
		Client, ClientError, ClientLoginError,
		ClientCookieExpiredError, ClientLoginRequiredError,
		__version__ as client_version)

import redis


def to_json(python_object):
	if isinstance(python_object, bytes):
		return {'__class__': 'bytes',
				'__value__': codecs.encode(python_object, 'base64').decode()}
	raise TypeError(repr(python_object) + ' is not JSON serializable')


def from_json(json_object):
	if '__class__' in json_object and json_object.get('__class__') == 'bytes':
		return codecs.decode(json_object.get('__value__').encode(), 'base64')
	return json_object


def onlogin_callback(api, setting_name):
	cache_settings = api.settings
	redis_client.setex(setting_name, 7776000000, json.dumps(cache_settings, default=to_json))
	print('[+] New auth cookie file was made: {0!s}'.format(setting_name))

def login(username, password):
	device_id = None
	try:
		settings_file = "credentials.json"
		credential = redis_client.get('credentials')
		if credential is None:
			api = Client(
				username, password,
				on_login=lambda x: onlogin_callback(x, 'credentials'))
		else:
			cached_settings = json.loads(credential, object_hook=from_json)
			device_id = cached_settings.get('device_id')
			# reuse auth settings
			api = Client(
				username, password,
				settings=cached_settings)
			print('[+] Using cached login cookie for "' + api.authenticated_user_name + '".')
	except (ClientCookieExpiredError, ClientLoginRequiredError) as e:
		print('ClientCookieExpiredError/ClientLoginRequiredError: {0!s}'.format(e))

		# Login expired
		# Do relogin but use default ua, keys and such
		api = Client(
			username, password,
			device_id=device_id,
			on_login=lambda x: onlogin_callback(x, settings_file))

	except ClientLoginError as e:
		print('[!] Could not login: {:s}.\n[!] {:s}\n\n{:s}'.format(
			json.loads(e.error_response).get("error_title", "Error title not available."),
			json.loads(e.error_response).get("message", "Not available"), e.error_response))
		print('-' * 70)
		sys.exit(9)
	except ClientError as e:
		print('[!] Client Error: {:s}'.format(e.error_response))
		print('-' * 70)
		sys.exit(9)
	except Exception as e:
		if str(e).startswith("unsupported pickle protocol"):
			print("[W] This cookie file is not compatible with Python {}.".format(sys.version.split(' ')[0][0]))
			print("[W] Please delete your cookie file 'credentials.json' and try again.")
		else:
			print('[!] Unexpected Exception: {0!s}'.format(e))
		print('-' * 70)
		sys.exit(99)

	print('[+] Login to "' + api.authenticated_user_name + '" OK!')
	cookie_expiry = api.cookie_jar.auth_expires
	print('[+] Login cookie expiry date: {0!s}'.format(
		datetime.datetime.fromtimestamp(cookie_expiry).strftime('%Y-%m-%d at %I:%M:%S %p')))

	return api

def like_post(post_id):
	like = ig_client.post_like(post_id)
	return like

def latest_post(username, user_id):
	try:
		today = datetime.date.today()
		t = time.mktime(datetime.datetime.strptime(str(today), "%Y-%m-%d").timetuple())
		t = int(t)
		feed = ig_client.user_feed(user_id, min_timestamp=str(t))
		f = open("feeds.json", "w")
		f.write(json.dumps(feed))
		f.close()

		for post in feed['items']:
			list_media = []
			post_id = post['id']
			pk = post['code']
			k = '{}:{}:{}'.format("post", username, pk)
			exist = redis_client.exists(k)
			if exist == 1:
				print(pk + " Exist")
				continue
			media_type = "photo" if post['media_type'] == 1 else "video"
			if "carousel_media" in post:
				carousel = True
				for i, cs in enumerate(post['carousel_media'], start=1):
					carousel_media_type = "photo" if cs['media_type'] == 1 else "video"
					if carousel_media_type == 'photo':
						list_media.append({
							"caption":"Photo #{}".format(i),
							"type":"photo",
							"media":cs['image_versions2']['candidates'][0]['url']
						})
					else:
						list_media.append({
							"caption":"Video #{}".format(i),						
							"type":"video",
							"media":cs['video_versions'][0]['url']
						})
			else:
				carousel = False
				if media_type == 'photo':
					url_media = post['image_versions2']['candidates'][0]['url']
				else:
					url_media = post['video_versions'][0]['url']
			post_url = "https://instagram.com/p/{}".format(pk)
			caption = "[POST] from {}\n\n{}\n\nLink: {}".format(username, post['caption']['text'], post_url)
			if len(caption) > 1000:
				caption = caption[:1000] + '...'
				
			like = like_post(post_id)
			
			print(pk + " Sending...")
			if carousel is True:
				send_telegram.send_media_group(caption=caption, media=list_media)
			else:
				send_telegram.telegram_bot_send_media(fileType=media_type, url=url_media, caption=caption)
			print(pk + " OK")
			redis_client.setex(k, 86400, "True")
	except Exception as e:
		print(e)

def latest_stories(username, user_id):
	feed = ig_client.user_story_feed(user_id)
	if feed['reel'] is None:
		print('No Update')
		return False
	taken_at = True
	feed_json = feed['reel']['items']

	list_video = []
	list_image = []

	for media in feed_json:
		if not taken_at:
			taken_ts = None
		else:
			if media.get('imported_taken_at'):
				taken_ts = datetime.datetime.utcfromtimestamp(media.get('imported_taken_at', "")).strftime(
					'%Y-%m-%d %H:%M:%S')
			else:
				taken_ts = datetime.datetime.utcfromtimestamp(media.get('taken_at', "")).strftime(
					'%Y-%m-%d %H:%M:%S')

		is_video = 'video_versions' in media and 'image_versions2' in media
		pk = media['code']
		k = '{}:{}:{}:{}'.format("story", username, "video" if is_video else "photo", pk)
		exist = redis_client.exists(k)

		if exist == 0:
			print('{} Sending...'.format(pk))
			caption = "[STORY] from {}"
			if is_video:
				data_media = {
					'url': media['video_versions'][0]['url'],
					'taken': taken_ts
				}
				# caption = "[VIDEO] from {}"
				list_video.append(data_media)
				send_telegram.telegram_bot_send_media(fileType='video', url=data_media['url'], caption=caption.format(username))
			else:
				data_media = {
					'url': media['image_versions2']['candidates'][0]['url'],
					'taken': taken_ts
				}
				# caption = "[PHOTO] from {}"
				list_image.append(data_media)
				send_telegram.telegram_bot_send_media(fileType='photo', url=data_media['url'], caption=caption.format(username))
			print('{} OK'.format(pk))
			redis_client.setex(k, 86400, json.dumps(data_media))
		else:
			print(pk + ' Exists')
	return feed

def download_user(user, attempt=0):
	try:
		if not user.isdigit():
			user_res = ig_client.username_info(user)
			user_id = user_res['user']['pk']
		else:
			user_id = user
			user_info = ig_client.user_info(user_id)
			if not user_info.get("user", None):
				raise Exception("No user is associated with the given user id.")
			else:
				user = user_info.get("user").get("username")
		if "feed" in sys.argv:
			print("[=] Fetch POST [=]")
			latest_post(user, user_id)
		if "story" in sys.argv:
			print("[=] Fetch STORY [=]")
			latest_stories(user, user_id)
		return user
	except Exception as e:
		print(e)

def start():
	oshi = os.getenv('OSHI_USERNAME')
	oshi = oshi.split(',')
	print('------------------------------')
	for o in oshi:
		print("Oshi: "+ o)
		download_user(o)

if __name__ == '__main__':
	load_dotenv()
	try:
		redis_client = redis.Redis(host=os.getenv('REDIS_HOST'), port=os.getenv('REDIS_PORT'), db=os.getenv('REDIS_DB'), password=os.getenv('REDIS_PASSWORD'))
		print("Connection to redis has been established...")
	except Exception as e:
		print("Cannot connect to redis...")
		print(e)
		sys.exit(9)
	username = os.getenv('INSTAGRAM_USER')
	password = os.getenv('INSTAGRAM_PASS')
	ig_client = login(username, password)
	start()
