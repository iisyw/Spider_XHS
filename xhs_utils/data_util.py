import json
import os
import re
import time
import csv
import openpyxl
import requests
from loguru import logger
from retry import retry


def norm_str(str):
    new_str = re.sub(r"|[\\/:*?\"<>| ]+", "", str).replace('\n', '').replace('\r', '')
    return new_str

def norm_text(text):
    ILLEGAL_CHARACTERS_RE = re.compile(r'[\000-\010]|[\013-\014]|[\016-\037]')
    text = ILLEGAL_CHARACTERS_RE.sub(r'', text)
    return text


def timestamp_to_str(timestamp):
    time_local = time.localtime(timestamp / 1000)
    dt = time.strftime("%Y-%m-%d %H:%M:%S", time_local)
    return dt

# 检查下载记录CSV文件是否存在，不存在则创建
def check_or_create_download_record(csv_path, user_id):
    csv_file = os.path.join(csv_path, f'{user_id}_download_record.csv')
    if not os.path.exists(csv_file):
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['note_id', 'user_id', 'note_type', 'title', 'desc', 'download_time', 'is_complete'])
        logger.info(f'创建下载记录文件 {csv_file}')
    return csv_file

# 检查笔记是否已下载并且下载是否完整
def check_download_status(note_info, media_path, csv_path):
    note_id = note_info['note_id']
    user_id = note_info['user_id']
    title = norm_str(note_info['title'])
    nickname = norm_str(note_info['nickname'])
    note_type = note_info['note_type']
    
    # 检查CSV记录
    csv_file = check_or_create_download_record(csv_path, user_id)
    is_downloaded = False
    is_complete_in_csv = False
    
    # 读取下载记录
    if os.path.exists(csv_file):
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # 跳过表头
            
            for row in reader:
                if row and row[0] == note_id:
                    is_downloaded = True
                    # 更严格地检查"True"和"False"字符串
                    if row[6].strip().lower() == 'true':
                        is_complete_in_csv = True
                    break
    
    save_path = f'{media_path}/{nickname}_{user_id}/{title}_{note_id}'
    
    # 即使CSV显示完整，也进行基本文件检查
    # 先检查目录和info.json是否存在
    if not os.path.exists(save_path) or not os.path.exists(f'{save_path}/info.json'):
        logger.warning(f"笔记 {note_id} 的CSV记录显示完整，但文件夹或info.json不存在")
        # 修改：如果物理文件不存在，无论CSV记录如何，都视为未下载，触发全新下载
        return False, False, csv_file
    
    # 读取info.json获取笔记信息
    try:
        with open(f'{save_path}/info.json', 'r', encoding='utf-8') as f:
            stored_note_info = json.loads(f.read().strip())
        
        # 如果CSV记录显示完整，只进行快速检查（文件数量而非内容）
        if is_complete_in_csv:
            # 检查图片数量
            expected_image_count = len(stored_note_info.get('image_list', []))
            actual_image_count = sum(1 for f in os.listdir(save_path) if f.startswith('image_') and f.endswith('.jpg'))
            
            if actual_image_count < expected_image_count:
                logger.warning(f"笔记 {note_id} 的CSV记录显示完整，但图片数量不足 (找到 {actual_image_count}/{expected_image_count})")
                return is_downloaded, False, csv_file
            
            # 检查视频数量(对于纯视频类型)
            if note_type == '视频' and stored_note_info.get('video_addr'):
                if not os.path.exists(f'{save_path}/video.mp4'):
                    logger.warning(f"笔记 {note_id} 的CSV记录显示完整，但视频文件不存在")
                    return is_downloaded, False, csv_file
            
            # 检查图集视频的视频数量
            if note_type == '图集视频' and 'video_image_mapping' in stored_note_info:
                expected_video_count = len(stored_note_info.get('video_image_mapping', {}))
                actual_video_count = sum(1 for f in os.listdir(save_path) if f.startswith('live_video_') and f.endswith('.mp4'))
                
                if actual_video_count < expected_video_count:
                    logger.warning(f"笔记 {note_id} 的CSV记录显示完整，但视频数量不足 (找到 {actual_video_count}/{expected_video_count})")
                    return is_downloaded, False, csv_file
            
            # 如果基本检查通过，信任CSV记录
            logger.debug(f"笔记 {note_id} 快速检查通过，信任CSV记录的完整性标记")
            return is_downloaded, True, csv_file
        
        # 如果CSV未标记为完整，则进行详细检查
        is_complete = True
        
        # 检查图片是否完整
        if note_type in ['图集', '图集视频']:
            for img_index, _ in enumerate(stored_note_info.get('image_list', [])):
                if not os.path.exists(f'{save_path}/image_{img_index}.jpg'):
                    is_complete = False
                    return is_downloaded, is_complete, csv_file
        
        # 检查普通视频是否完整
        if note_type == '视频' and stored_note_info.get('video_addr'):
            if not os.path.exists(f'{save_path}/video.mp4'):
                is_complete = False
                return is_downloaded, is_complete, csv_file
        
        # 检查图集视频中的视频是否完整
        if note_type == '图集视频' and 'video_image_mapping' in stored_note_info:
            for video_index, img_index in stored_note_info.get('video_image_mapping', {}).items():
                if not os.path.exists(f'{save_path}/live_video_{img_index}.mp4'):
                    is_complete = False
                    return is_downloaded, is_complete, csv_file
        
        # 如果所有检查都通过，标记为完整
        return is_downloaded, True, csv_file
    
    except Exception as e:
        logger.warning(f"检查笔记 {note_id} 完整性时出错: {e}")
        return is_downloaded, False, csv_file

# 更新下载记录
def update_download_record(csv_file, note_info, is_complete):
    note_id = note_info['note_id']
    user_id = note_info['user_id']
    title = norm_str(note_info['title'])
    note_type = note_info['note_type']
    # 添加描述字段
    desc = note_info.get('desc', '')
    download_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    
    # 读取现有记录
    rows = []
    updated = False
    
    if os.path.exists(csv_file):
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header_row = next(reader)
            rows.append(header_row)
            
            for row in reader:
                if not row:
                    continue
                    
                if row[0] == note_id:
                    # 更新现有记录
                    row[4] = desc
                    row[5] = download_time
                    row[6] = str(is_complete)
                    updated = True
                
                rows.append(row)
    
    # 如果没有现有记录，添加新记录
    if not updated:
        rows.append([note_id, user_id, note_type, title, desc, download_time, str(is_complete)])
    
    # 写回文件
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(rows)

# 新增函数：在下载前创建笔记记录
def create_note_record(note_info, csv_path):
    """
    在下载前创建笔记记录，用于推送通知和防止重复下载
    :param note_info: 笔记信息字典，包含note_id, user_id等字段
    :param csv_path: CSV文件保存路径
    :return: 笔记是否已存在于记录中，CSV文件路径
    """
    if not csv_path:
        return False, None
        
    note_id = note_info['note_id']
    user_id = note_info['user_id']
    title = norm_str(note_info.get('title', '无标题')) 
    note_type = note_info.get('note_type', '未知类型')
    desc = note_info.get('desc', '')
    
    # 检查CSV记录是否存在
    csv_file = check_or_create_download_record(csv_path, user_id)
    is_existing = False
    
    # 读取现有记录
    rows = []
    if os.path.exists(csv_file):
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header_row = next(reader)
            rows.append(header_row)
            
            for row in reader:
                if not row:
                    continue
                
                # 检查笔记是否已存在
                if row[0] == note_id:
                    is_existing = True
                    # 保留原有记录
                    rows.append(row)
                else:
                    # 其他记录保持不变
                    rows.append(row)
    
    # 如果笔记不存在，添加新记录
    if not is_existing:
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        # 新笔记默认标记为未完成下载
        new_row = [note_id, user_id, note_type, title, desc, current_time, "False"]
        rows.append(new_row)
        
        # 写回文件
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        
        logger.info(f"新建笔记记录: {note_id}, 标题: {title}")
    
    return is_existing, csv_file

def handle_user_info(data, user_id):
    home_url = f'https://www.xiaohongshu.com/user/profile/{user_id}'
    nickname = data['basic_info']['nickname']
    avatar = data['basic_info']['imageb']
    red_id = data['basic_info']['red_id']
    gender = data['basic_info']['gender']
    if gender == 0:
        gender = '男'
    elif gender == 1:
        gender = '女'
    else:
        gender = '未知'
    ip_location = data['basic_info']['ip_location']
    desc = data['basic_info']['desc']
    follows = data['interactions'][0]['count']
    fans = data['interactions'][1]['count']
    interaction = data['interactions'][2]['count']
    tags_temp = data['tags']
    tags = []
    for tag in tags_temp:
        try:
            tags.append(tag['name'])
        except:
            pass
    return {
        'user_id': user_id,
        'home_url': home_url,
        'nickname': nickname,
        'avatar': avatar,
        'red_id': red_id,
        'gender': gender,
        'ip_location': ip_location,
        'desc': desc,
        'follows': follows,
        'fans': fans,
        'interaction': interaction,
        'tags': tags,
    }

def handle_note_info(data):
    note_id = data['id']
    note_url = data['url']
    note_type = data['note_card']['type']
    
    # 检查笔记类型
    has_videos_in_images = False
    logger.debug(f"笔记 {note_id} 原始类型: {note_type}")
    logger.debug(f"笔记 {note_id} note_card keys: {data['note_card'].keys()}")
    
    if note_type == 'normal':
        # 检查是否有带视频的图片（live_photo=true）
        image_list_temp = data['note_card']['image_list']
        logger.debug(f"笔记 {note_id} 图片数量: {len(image_list_temp)}")
        
        # 详细检查每张图片是否包含live_photo属性
        for i, image in enumerate(image_list_temp):
            logger.debug(f"笔记 {note_id} 图片{i} keys: {image.keys()}")
            if 'live_photo' in image:
                logger.debug(f"笔记 {note_id} 图片{i} live_photo: {image['live_photo']}")
            
            # 检查是否包含视频相关属性
            if image.get('live_photo') == True:
                logger.debug(f"笔记 {note_id} 图片{i} 包含live_photo标记")
                
                # 检查stream字段
                if 'stream' in image:
                    logger.debug(f"笔记 {note_id} 图片{i} stream keys: {image['stream'].keys()}")
                    
                    # 检查h264字段
                    if 'h264' in image['stream']:
                        logger.debug(f"笔记 {note_id} 图片{i} 确认包含视频流")
                        has_videos_in_images = True
                        break
                # 尝试其他可能的字段结构
                elif 'video' in image or 'video_id' in image:
                    logger.debug(f"笔记 {note_id} 图片{i} 通过替代方法检测到视频")
                    has_videos_in_images = True
                    break
        
        if has_videos_in_images:
            note_type = '图集视频'
            logger.debug(f"笔记 {note_id} 最终判定为图集视频类型")
        else:
            note_type = '图集'
            logger.debug(f"笔记 {note_id} 最终判定为普通图集类型")
    else:
        note_type = '视频'
        logger.debug(f"笔记 {note_id} 最终判定为纯视频类型")
        
    user_id = data['note_card']['user']['user_id']
    home_url = f'https://www.xiaohongshu.com/user/profile/{user_id}'
    nickname = data['note_card']['user']['nickname']
    avatar = data['note_card']['user']['avatar']
    title = data['note_card']['title']
    if title.strip() == '':
        title = f'无标题'
    desc = data['note_card']['desc']
    liked_count = data['note_card']['interact_info']['liked_count']
    collected_count = data['note_card']['interact_info']['collected_count']
    comment_count = data['note_card']['interact_info']['comment_count']
    share_count = data['note_card']['interact_info']['share_count']
    
    # 处理图片列表
    image_list_temp = data['note_card']['image_list']
    image_list = []
    live_videos_list = []  # 存储图片中包含的视频URL
    video_image_mapping = {}  # 存储视频与图片的对应关系
    
    for img_index, image in enumerate(image_list_temp):
        try:
            # 添加图片URL
            image_list.append(image['info_list'][1]['url'])
            
            # 如果是live_photo，尝试多种方式提取视频URL
            has_live_video = False
            if image.get('live_photo') == True:
                # 标准路径: 通过stream/h264获取视频URL
                if 'stream' in image and 'h264' in image['stream']:
                    for video_info in image['stream']['h264']:
                        if 'master_url' in video_info:
                            live_videos_list.append(video_info['master_url'])
                            video_image_mapping[len(live_videos_list)-1] = img_index
                            has_live_video = True
                            break
                
                # 备选路径1: 直接查找video_addr字段
                elif 'video_addr' in image:
                    live_videos_list.append(image['video_addr'])
                    video_image_mapping[len(live_videos_list)-1] = img_index
                    has_live_video = True
                
                # 备选路径2: 查找其他可能的视频URL字段
                elif 'video' in image and isinstance(image['video'], dict):
                    for key in ['url', 'master_url', 'consumer_url']:
                        if key in image['video']:
                            live_videos_list.append(image['video'][key])
                            video_image_mapping[len(live_videos_list)-1] = img_index
                            has_live_video = True
                            break
                
                # 记录调试信息
                if has_live_video:
                    logger.debug(f"笔记 {note_id} 成功提取图片{img_index}对应的视频")
                else:
                    logger.debug(f"笔记 {note_id} 图片{img_index}标记为live_photo，但无法提取视频URL")
                    if 'stream' in image:
                        logger.debug(f"笔记 {note_id} 图片{img_index} stream内容: {image['stream']}")
        except Exception as e:
            logger.debug(f"笔记 {note_id} 处理图片{img_index}时出错: {e}")
    
    # 如果成功提取了视频URL，但类型不是图集视频，则更新类型
    if live_videos_list and note_type != '图集视频':
        logger.debug(f"笔记 {note_id} 存在{len(live_videos_list)}个图集视频，但类型是{note_type}，更正为图集视频")
        note_type = '图集视频'
    
    # 处理常规视频
    video_cover = None
    video_addr = None
    if note_type == '视频' and 'video' in data['note_card'] and 'consumer' in data['note_card']['video']:
        video_cover = image_list[0] if image_list else None
        video_addr = 'https://sns-video-bd.xhscdn.com/' + data['note_card']['video']['consumer']['origin_video_key']
    
    tags_temp = data['note_card']['tag_list']
    tags = []
    for tag in tags_temp:
        try:
            tags.append(tag['name'])
        except:
            pass
    upload_time = timestamp_to_str(data['note_card']['time'])
    if 'ip_location' in data['note_card']:
        ip_location = data['note_card']['ip_location']
    else:
        ip_location = '未知'
        
    result = {
        'note_id': note_id,
        'note_url': note_url,
        'note_type': note_type,
        'user_id': user_id,
        'home_url': home_url,
        'nickname': nickname,
        'avatar': avatar,
        'title': title,
        'desc': desc,
        'liked_count': liked_count,
        'collected_count': collected_count,
        'comment_count': comment_count,
        'share_count': share_count,
        'video_cover': video_cover,
        'video_addr': video_addr,
        'image_list': image_list,
        'live_videos_list': live_videos_list,  # 图集中的视频URL列表
        'video_image_mapping': video_image_mapping,  # 视频与图片的对应关系
        'tags': tags,
        'upload_time': upload_time,
        'ip_location': ip_location,
    }
    
    logger.debug(f"笔记 {note_id} 最终类型: {note_type}, 图片数: {len(image_list)}, 视频数: {len(live_videos_list) if note_type=='图集视频' else ('1' if note_type=='视频' else '0')}")
    return result

def handle_comment_info(data):
    note_id = data['note_id']
    note_url = data['note_url']
    comment_id = data['id']
    user_id = data['user_info']['user_id']
    home_url = f'https://www.xiaohongshu.com/user/profile/{user_id}'
    nickname = data['user_info']['nickname']
    avatar = data['user_info']['image']
    content = data['content']
    show_tags = data['show_tags']
    like_count = data['like_count']
    upload_time = timestamp_to_str(data['create_time'])
    try:
        ip_location = data['ip_location']
    except:
        ip_location = '未知'
    pictures = []
    try:
        pictures_temp = data['pictures']
        for picture in pictures_temp:
            try:
                pictures.append(picture['info_list'][1]['url'])
                # success, msg, img_url = XHS_Apis.get_note_no_water_img(picture['info_list'][1]['url'])
                # pictures.append(img_url)
            except:
                pass
    except:
        pass
    return {
        'note_id': note_id,
        'note_url': note_url,
        'comment_id': comment_id,
        'user_id': user_id,
        'home_url': home_url,
        'nickname': nickname,
        'avatar': avatar,
        'content': content,
        'show_tags': show_tags,
        'like_count': like_count,
        'upload_time': upload_time,
        'ip_location': ip_location,
        'pictures': pictures,
    }
def save_to_xlsx(datas, file_path, type='note'):
    wb = openpyxl.Workbook()
    ws = wb.active
    if type == 'note':
        headers = ['笔记id', '笔记url', '笔记类型', '用户id', '用户主页url', '昵称', '头像url', '标题', '描述', '点赞数量', '收藏数量', '评论数量', '分享数量', '视频封面url', '视频地址url', '图片地址url列表', '图集中的视频url列表', '标签', '上传时间', 'ip归属地']
    elif type == 'user':
        headers = ['用户id', '用户主页url', '用户名', '头像url', '小红书号', '性别', 'ip地址', '介绍', '关注数量', '粉丝数量', '作品被赞和收藏数量', '标签']
    else:
        headers = ['笔记id', '笔记url', '评论id', '用户id', '用户主页url', '昵称', '头像url', '评论内容', '评论标签', '点赞数量', '上传时间', 'ip归属地', '图片地址url列表']
    ws.append(headers)
    for data in datas:
        # 确保所有字段都存在
        if type == 'note' and 'live_videos_list' not in data:
            data['live_videos_list'] = []
        
        data = {k: norm_text(str(v)) for k, v in data.items()}
        ws.append(list(data.values()))
    wb.save(file_path)
    logger.info(f'数据保存至 {file_path}')

def download_media(path, name, url, type):
    if type == 'image':
        content = requests.get(url).content
        with open(path + '/' + name + '.jpg', mode="wb") as f:
            f.write(content)
    elif type == 'video':
        res = requests.get(url, stream=True)
        size = 0
        chunk_size = 1024 * 1024
        with open(path + '/' + name + '.mp4', mode="wb") as f:
            for data in res.iter_content(chunk_size=chunk_size):
                f.write(data)
                size += len(data)

def save_user_detail(user, path):
    with open(f'{path}/detail.txt', mode="w", encoding="utf-8") as f:
        # 逐行输出到txt里
        f.write(f"用户id: {user['user_id']}\n")
        f.write(f"用户主页url: {user['home_url']}\n")
        f.write(f"用户名: {user['nickname']}\n")
        f.write(f"头像url: {user['avatar']}\n")
        f.write(f"小红书号: {user['red_id']}\n")
        f.write(f"性别: {user['gender']}\n")
        f.write(f"ip地址: {user['ip_location']}\n")
        f.write(f"介绍: {user['desc']}\n")
        f.write(f"关注数量: {user['follows']}\n")
        f.write(f"粉丝数量: {user['fans']}\n")
        f.write(f"作品被赞和收藏数量: {user['interaction']}\n")
        f.write(f"标签: {user['tags']}\n")

def save_note_detail(note, path):
    with open(f'{path}/detail.txt', mode="w", encoding="utf-8") as f:
        # 逐行输出到txt里
        f.write(f"笔记id: {note['note_id']}\n")
        f.write(f"笔记url: {note['note_url']}\n")
        f.write(f"笔记类型: {note['note_type']}\n")
        f.write(f"用户id: {note['user_id']}\n")
        f.write(f"用户主页url: {note['home_url']}\n")
        f.write(f"昵称: {note['nickname']}\n")
        f.write(f"头像url: {note['avatar']}\n")
        f.write(f"标题: {note['title']}\n")
        f.write(f"描述: {note['desc']}\n")
        f.write(f"点赞数量: {note['liked_count']}\n")
        f.write(f"收藏数量: {note['collected_count']}\n")
        f.write(f"评论数量: {note['comment_count']}\n")
        f.write(f"分享数量: {note['share_count']}\n")
        f.write(f"视频封面url: {note['video_cover']}\n")
        f.write(f"视频地址url: {note['video_addr']}\n")
        f.write(f"图片地址url列表: {note['image_list']}\n")
        
        if 'live_videos_list' in note and note['live_videos_list']:
            f.write(f"图集中的视频url列表: {note['live_videos_list']}\n")
            
            # 显示视频与图片的对应关系
            if 'video_image_mapping' in note and note['video_image_mapping']:
                f.write("视频与图片的对应关系:\n")
                for video_idx, img_idx in note['video_image_mapping'].items():
                    f.write(f"  视频索引 {video_idx} → 图片索引 {img_idx} (下载为live_video_{img_idx}.mp4)\n")
        
        f.write(f"标签: {note['tags']}\n")
        f.write(f"上传时间: {note['upload_time']}\n")
        f.write(f"ip归属地: {note['ip_location']}\n")



@retry(tries=3, delay=1)
def download_note(note_info, path, raw_data=None, csv_path=None):
    note_id = note_info['note_id']
    user_id = note_info['user_id']
    title = note_info['title']
    title = norm_str(title)
    nickname = note_info['nickname']
    nickname = norm_str(nickname)
    if title.strip() == '':
        title = f'无标题'
        
    save_path = f'{path}/{nickname}_{user_id}/{title}_{note_id}'
    
    # 如果提供了csv_path，检查下载状态，避免重复下载
    already_downloaded = False
    is_complete = False
    csv_file = None
    
    if csv_path:
        already_downloaded, is_complete, csv_file = check_download_status(note_info, path, csv_path)
        
    note_type = note_info['note_type']
    note_desc = f"{note_type}笔记 [{title}_{note_id}] (作者: {nickname})"
    
    # 如果已经完整下载，则跳过
    if already_downloaded and is_complete:
        logger.info(f"✓ {note_desc} 已完整下载，跳过下载")
        return save_path
    
    # 判断是全新下载还是更新下载
    is_new_download = not already_downloaded or not os.path.exists(save_path)
    if is_new_download:
        logger.info(f"↓ {note_desc} 开始全新下载")
    else:
        logger.info(f"⤵ {note_desc} 更新下载")
        
    # 创建目录并保存基本信息
    check_and_create_path(save_path)
    
    # 无论是否已下载过，始终保存最新的笔记信息和详情
    with open(f'{save_path}/info.json', mode='w', encoding='utf-8') as f:
        f.write(json.dumps(note_info) + '\n')
    
    if raw_data:
        with open(f'{save_path}/raw_info.json', mode='w', encoding='utf-8') as f:
            f.write(json.dumps(raw_data) + '\n')
    
    save_note_detail(note_info, save_path)
    
    # 如果已下载但不完整，只下载缺失的部分
    missing_files = []
    if already_downloaded and not is_new_download:
        # 判断哪些内容需要重新下载并收集缺失的文件
        if note_type in ['图集', '图集视频']:
            # 检查和下载缺失的图片
            for img_index, img_url in enumerate(note_info['image_list']):
                img_file = f'{save_path}/image_{img_index}.jpg'
                if not os.path.exists(img_file):
                    missing_files.append(f'image_{img_index}.jpg')
                    logger.info(f'  下载缺失的图片: image_{img_index}.jpg')
                    download_media(save_path, f'image_{img_index}', img_url, 'image')
        
        if note_type == '视频' and note_info['video_addr']:
            # 检查和下载缺失的视频
            video_file = f'{save_path}/video.mp4'
            if not os.path.exists(video_file) and note_info['video_addr']:
                missing_files.append('video.mp4')
                logger.info(f'  下载缺失的视频: video.mp4')
                download_media(save_path, 'video', note_info['video_addr'], 'video')
                if note_info['video_cover'] and not os.path.exists(f'{save_path}/cover.jpg'):
                    missing_files.append('cover.jpg')
                    logger.info(f'  下载缺失的视频封面: cover.jpg')
                    download_media(save_path, 'cover', note_info['video_cover'], 'image')
        
        if note_type == '图集视频' and 'live_videos_list' in note_info and 'video_image_mapping' in note_info:
            # 检查和下载缺失的图集视频，只下载有映射关系的视频
            for video_index, img_index in note_info['video_image_mapping'].items():
                # 确保video_index是有效的索引
                if int(video_index) < len(note_info['live_videos_list']):
                    video_url = note_info['live_videos_list'][int(video_index)]
                    video_file = f'{save_path}/live_video_{img_index}.mp4'
                    if not os.path.exists(video_file):
                        missing_files.append(f'live_video_{img_index}.mp4')
                        logger.info(f'  下载缺失的图集视频: live_video_{img_index}.mp4')
                        download_media(save_path, f'live_video_{img_index}', video_url, 'video')
        
        # 如果找到了缺失文件，则显示提示；否则标记为完整
        if missing_files:
            logger.info(f"⚠ {note_desc} 存在已下载文件但不完整，正在下载以上{len(missing_files)}个缺失文件")
        else:
            logger.info(f"✓ {note_desc} 所有文件已存在，无需下载")
            is_complete = True
    else:
        # 首次下载，完整下载所有内容
        # 删除重复的日志记录，已经在前面记录过了
        
        if note_type == '图集':
            # 纯图集类型
            logger.info(f"  下载{len(note_info['image_list'])}张图片")
            for img_index, img_url in enumerate(note_info['image_list']):
                download_media(save_path, f'image_{img_index}', img_url, 'image')
        
        elif note_type == '视频':
            # 纯视频类型
            logger.info(f"  下载1个视频")
            if note_info['video_cover']:
                download_media(save_path, 'cover', note_info['video_cover'], 'image')
            if note_info['video_addr']:
                download_media(save_path, 'video', note_info['video_addr'], 'video')
        
        elif note_type == '图集视频':
            # 图集+视频混合类型
            # 1. 下载所有图片
            img_count = len(note_info['image_list'])
            logger.info(f"  下载{img_count}张图片")
            for img_index, img_url in enumerate(note_info['image_list']):
                download_media(save_path, f'image_{img_index}', img_url, 'image')
            
            # 2. 下载所有视频，使用映射关系保持序号一致，只下载有映射关系的视频
            if 'live_videos_list' in note_info and 'video_image_mapping' in note_info:
                video_count = len(note_info['video_image_mapping'])
                logger.info(f"  下载{video_count}个图片对应的视频")
                for video_index, img_index in note_info['video_image_mapping'].items():
                    # 确保video_index是有效的索引
                    if int(video_index) < len(note_info['live_videos_list']):
                        video_url = note_info['live_videos_list'][int(video_index)]
                        download_media(save_path, f'live_video_{img_index}', video_url, 'video')
    
    # 检查下载是否完整（只在未标记完整的情况下进行）
    if not is_complete:
        is_complete = True
        incomplete_files = []
        
        # 检查图片
        if note_type in ['图集', '图集视频']:
            for img_index, _ in enumerate(note_info['image_list']):
                img_file = f'{save_path}/image_{img_index}.jpg'
                if not os.path.exists(img_file):
                    is_complete = False
                    incomplete_files.append(img_file)
        
        # 检查视频
        if note_type == '视频' and note_info['video_addr']:
            video_file = f'{save_path}/video.mp4'
            if not os.path.exists(video_file):
                is_complete = False
                incomplete_files.append(video_file)
        
        # 检查图集视频 - 修复完整性检查逻辑，只检查存在映射的视频
        if note_type == '图集视频' and 'live_videos_list' in note_info and 'video_image_mapping' in note_info:
            # 根据映射关系检查视频是否存在
            for video_index, img_index in note_info['video_image_mapping'].items():
                video_file = f'{save_path}/live_video_{img_index}.mp4'
                if not os.path.exists(video_file):
                    is_complete = False
                    incomplete_files.append(video_file)
    
    # 更新下载记录
    if csv_file:
        update_download_record(csv_file, note_info, is_complete)
    
    # 下载完成后的状态提示
    if is_complete:
        logger.info(f"✓ {note_desc} 下载完成")
    else:
        logger.warning(f"⚠ {note_desc} 下载不完整，缺少以下文件: {incomplete_files}")
    
    return save_path


def check_and_create_path(path):
    if not os.path.exists(path):
        os.makedirs(path)
