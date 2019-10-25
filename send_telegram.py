import os
import time
import requests
from dotenv import load_dotenv
import json

def telegram_bot_sendtext(bot_message):
    send_text = TELEGRAM_URL + BOT_TOKEN + '/sendMessage?chat_id={}&text={}'.format(CHAT_ID,bot_message)
    response = requests.get(send_text)
    response_json = response.json()
    return response.json()

def send_media_group(**kwargs):
    caption = kwargs.get('caption')
    media = kwargs.get('media')
    carousel = kwargs.get('carousel', None)

    send_text = telegram_bot_sendtext(caption);
    if send_text['ok'] is not True:
        print('Stop')
        return
    else:
        message_id = send_text.get('result')['message_id']

    data = {
        'chat_id' : CHAT_ID,
        "reply_to_message_id":message_id,
        "media": json.dumps(media)
    }
    send_url = TELEGRAM_URL + '{}{}'.format(BOT_TOKEN, '/sendMediaGroup') 
    response = requests.post(send_url, data=data)
    response_json = response.json()
    if response_json.get('ok') is True:
        print('DONE')
    return response_json

def telegram_bot_send_media(**kwargs):
    fileType = kwargs.get('fileType')
    url = kwargs.get('url', None)
    caption = kwargs.get('caption')
    reply_first = kwargs.get('reply_first', False)
    reply_id = kwargs.get('reply_id', None)
    data = {
        'chat_id' : CHAT_ID,
        "caption": caption,
    }
    if reply_first is True:
        send_text = telegram_bot_sendtext(caption);
        if send_text['ok'] is not True:
            print('Stop')
            return
        data.update({"reply_to_message_id": send_text.get('result')['message_id']})
    if reply_id is not None: data.update({"reply_to_message_id": reply_id})
    if fileType == 'video':
        data.update({
            'video': url
        })
        endpoint = "/sendVideo"
    elif fileType == 'photo':
        data.update({
            'photo': url
        })
        endpoint = "/sendPhoto"
    else:
        print("Failed")
        return False

    send_url = TELEGRAM_URL + '{}{}'.format(BOT_TOKEN, endpoint) 
    response = requests.post(send_url,data=data)
    return response.json()


if __name__ == 'send_telegram':
    load_dotenv()
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    CHAT_ID = os.getenv('CHAT_ID')
    TELEGRAM_URL = os.getenv('TELEGRAM_URL')