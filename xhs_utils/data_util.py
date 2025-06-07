import json
import os
import re
import time
import csv
import openpyxl
import requests
from loguru import logger
from retry import retry
from collections import defaultdict
from openpyxl import Workbook
from urllib.parse import urlparse, unquote
import traceback


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
    folder_exists = os.path.exists(save_path)
    info_json_exists = os.path.exists(f'{save_path}/info.json')
    
    if not folder_exists or not info_json_exists:
        logger.debug(f"笔记 {note_id} 的CSV 记录显示完整，但文件夹或info.json不存在")
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

# 添加新函数用于检查笔记文件是否完整
def check_note_files_complete(note_id, csv_path=None, media_path=None):
    """
    检查笔记文件是否完整
    
    :param note_id: 笔记ID
    :param csv_path: CSV保存路径
    :param media_path: 媒体文件保存路径
    :return: 是否完整
    """
    if not csv_path or not media_path:
        return False
    
    # 默认为不完整
    is_complete = False
    user_id = None
    save_path = None
    
    # 1. 查找CSV记录
    csv_complete = False
    try:
        import glob
        import csv
        import os
        
        # 寻找包含该笔记ID的CSV文件
        for csv_file in glob.glob(os.path.join(csv_path, '*_download_record.csv')):
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # 跳过表头
                for row in reader:
                    if row and len(row) > 0 and row[0] == note_id:
                        # 找到笔记记录
                        user_id = os.path.basename(csv_file).replace('_download_record.csv', '')
                        # 检查是否标记为完成
                        if len(row) > 6 and row[6].strip().lower() == 'true':
                            csv_complete = True
                            # 检查CSV中记录的图片数量和视频数量
                            nickname = row[1] if len(row) > 1 else "未知用户"
                            title = row[3] if len(row) > 3 else "无标题"
                            
                            # 规范化标题和昵称
                            title = norm_str(title)
                            nickname = norm_str(nickname)
                            
                            # 构建保存路径
                            save_path = f"{media_path}/{nickname}_{user_id}/{title}_{note_id}"
                            break
            if csv_complete:
                break
                
        if not csv_complete or not save_path:
            # CSV不完整或未找到保存路径
            logger.debug(f"笔记 {note_id} 的CSV记录不存在或不完整")
            return False
            
        # 2. 检查文件夹和info.json
        folder_exists = os.path.exists(save_path)
        info_json_exists = os.path.exists(f'{save_path}/info.json')
        
        if not folder_exists or not info_json_exists:
            logger.debug(f"笔记 {note_id} 的CSV 记录显示完整，但文件夹或info.json不存在")
            return False
            
        # 3. 读取info.json获取笔记类型和预期文件信息
        import json
        with open(f'{save_path}/info.json', 'r', encoding='utf-8') as f:
            stored_note_info = json.loads(f.read().strip())
            
        # 4. 根据笔记类型检查媒体文件完整性
        note_type = stored_note_info.get('note_type', '')
        media_files_exist = False
        media_files_complete = False
        
        if note_type == '视频':
            # 视频类型检查video.mp4文件
            media_files_exist = os.path.exists(f'{save_path}/video.mp4')
            media_files_complete = media_files_exist
            
        elif note_type == '图集':
            # 图集类型检查所有图片文件
            expected_image_count = len(stored_note_info.get('image_list', []))
            actual_image_files = [f for f in os.listdir(save_path) if f.startswith('image_') and f.endswith('.jpg')]
            actual_image_count = len(actual_image_files)
            
            # 检查是否所有序号的图片都存在
            expected_image_indexes = set(range(expected_image_count))
            actual_image_indexes = set()
            for img_file in actual_image_files:
                try:
                    img_index = int(img_file.replace('image_', '').replace('.jpg', ''))
                    actual_image_indexes.add(img_index)
                except ValueError:
                    pass
            
            # 必须存在至少一张图片，且实际图片数量与预期相符
            media_files_exist = len(actual_image_files) > 0
            media_files_complete = expected_image_count == actual_image_count and expected_image_indexes == actual_image_indexes
            
            if not media_files_complete:
                logger.debug(f"笔记 {note_id} 图集不完整: 预期{expected_image_count}张, 实际{actual_image_count}张, 缺失的索引: {expected_image_indexes - actual_image_indexes}")
                
        elif note_type == '图集视频':
            # 图集视频类型需要检查所有图片和对应的视频
            # 1. 检查图片数量
            expected_image_count = len(stored_note_info.get('image_list', []))
            actual_image_files = [f for f in os.listdir(save_path) if f.startswith('image_') and f.endswith('.jpg')]
            actual_image_count = len(actual_image_files)
            
            # 2. 检查视频数量
            video_image_mapping = stored_note_info.get('video_image_mapping', {})
            expected_video_count = len(video_image_mapping)
            expected_video_image_indexes = {int(img_idx) for _, img_idx in video_image_mapping.items()}
            
            actual_video_files = [f for f in os.listdir(save_path) if f.startswith('live_video_') and f.endswith('.mp4')]
            actual_video_indexes = set()
            for video_file in actual_video_files:
                try:
                    video_index = int(video_file.replace('live_video_', '').replace('.mp4', ''))
                    actual_video_indexes.add(video_index)
                except ValueError:
                    pass
            
            # 必须有图片和视频，且图片和视频的数量与预期相符
            media_files_exist = len(actual_image_files) > 0 and len(actual_video_files) > 0
            images_complete = expected_image_count == actual_image_count
            videos_complete = expected_video_image_indexes.issubset(actual_video_indexes)
            media_files_complete = images_complete and videos_complete
            
            if not media_files_complete:
                if not images_complete:
                    logger.debug(f"笔记 {note_id} 图集视频的图片不完整: 预期{expected_image_count}张, 实际{actual_image_count}张")
                if not videos_complete:
                    logger.debug(f"笔记 {note_id} 图集视频的视频不完整: 预期{len(expected_video_image_indexes)}个, 实际{len(actual_video_indexes)}个, 缺失的索引: {expected_video_image_indexes - actual_video_indexes}")
        
        # 5. 判断最终完整性
        is_complete = folder_exists and info_json_exists and media_files_exist and media_files_complete
        
        if csv_complete and not is_complete:
            logger.debug(f"笔记 {note_id} 的CSV记录显示已完成，但文件不完整，需要重新下载")
            
    except Exception as e:
        logger.warning(f"检查笔记 {note_id} 文件完整性时出错: {e}")
        is_complete = False
        
    return is_complete

# 修改create_note_record函数以扩展CSV记录
def create_note_record(note_info, csv_path=None):
    """
    创建笔记的CSV记录
    
    :param note_info: 笔记信息
    :param csv_path: CSV保存路径
    :return: 是否已存在记录, CSV文件路径
    """
    if not csv_path:
        return False, None
    
    try:
        import os
        import csv
        
        # 获取基本信息
        note_id = note_info.get('note_id', '')
        user_id = note_info.get('user_id', '')
        nickname = note_info.get('nickname', '未知用户')
        note_type = note_info.get('note_type', '未知类型')
        title = note_info.get('title', '无标题')
        
        # 处理描述中的换行符，替换为空格
        desc = note_info.get('desc', '')
        desc = desc.replace('\n', ' ').replace('\r', ' ')
        
        create_time = note_info.get('create_time', '')
        is_complete = False
        
        # 获取图片和视频数量
        image_count = len(note_info.get('image_list', []))
        
        # 获取视频数量，根据笔记类型
        video_count = 0
        if note_type == '视频':
            video_count = 1 if note_info.get('video_addr') else 0
        elif note_type == '图集视频':
            video_count = len(note_info.get('live_videos_list', []))
        
        # 检查CSV文件是否存在
        csv_file = os.path.join(csv_path, f'{user_id}_download_record.csv')
        is_existing = False
        
        if os.path.exists(csv_file):
            # 读取现有记录
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                # 检查header
                if len(rows) > 0:
                    # 检查是否需要更新header
                    header = rows[0]
                    if len(header) < 9 or header[-2] != 'image_count' or header[-1] != 'video_count':
                        # 需要更新header，添加新字段
                        header.extend(['image_count', 'video_count'])
                        rows[0] = header
                
                # 检查是否已存在记录
                for i, row in enumerate(rows):
                    if i > 0 and len(row) > 0 and row[0] == note_id:
                        is_existing = True
                        # 更新现有记录，确保包含图片和视频数量
                        if len(row) < 9:  # 需要添加新字段
                            row.extend([str(image_count), str(video_count)])
                        else:  # 更新现有字段
                            row[-2] = str(image_count)
                            row[-1] = str(video_count)
                        rows[i] = row
                        break
                
                # 写回更新后的记录
                with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerows(rows)
            
            if not is_existing:
                # 追加新记录
                with open(csv_file, 'a', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([note_id, nickname, note_type, title, desc, create_time, str(is_complete), str(image_count), str(video_count)])
        else:
            # 创建新文件
            with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                # 写入表头
                writer.writerow(['note_id', 'nickname', 'note_type', 'title', 'desc', 'create_time', 'is_complete', 'image_count', 'video_count'])
                # 写入记录
                writer.writerow([note_id, nickname, note_type, title, desc, create_time, str(is_complete), str(image_count), str(video_count)])
        
        return is_existing, csv_file
    except Exception as e:
        from loguru import logger
        logger.error(f"创建笔记记录失败: {e}")
        return False, None

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
def download_video(video_url, save_path, filename="video.mp4"):
    """
    下载视频文件
    
    :param video_url: 视频URL
    :param save_path: 保存路径
    :param filename: 文件名
    :return: 是否成功
    """
    try:
        resp = requests.get(video_url, stream=True, timeout=30)
        if resp.status_code != 200:
            logger.error(f"下载视频失败: {resp.status_code}")
            return False
            
        # 确保目录存在
        os.makedirs(save_path, exist_ok=True)
        
        # 保存视频文件
        file_path = os.path.join(save_path, filename)
        with open(file_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=1024):
                f.write(chunk)
        
        return True
        
    except Exception as e:
        logger.error(f"下载视频时出错: {e}")
        return False

@retry(tries=3, delay=1)
def download_file(url, file_path, file_type="image"):
    """
    下载文件(图片或其他类型)
    
    :param url: 文件URL
    :param file_path: 保存路径(包含文件名)
    :param file_type: 文件类型
    :return: 是否成功
    """
    try:
        # 创建目录
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 下载文件
        resp = requests.get(url, stream=True, timeout=30)
        if resp.status_code != 200:
            logger.error(f"下载{file_type}失败: {resp.status_code}")
            return False
            
        # 保存文件
        with open(file_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=1024):
                f.write(chunk)
                
        return True
        
    except Exception as e:
        logger.error(f"下载{file_type}时出错: {e}")
        return False

@retry(tries=3, delay=1)
def download_note(note_info, save_path, raw_data, csv_path=None):
    """下载笔记中的图片和视频
    此函数源自：https://github.com/JoeanAmier/XHS-Downloader/blob/master/src/downloader/resources.py
    感谢原作者的贡献

    Args:
        note_info: 笔记数据，经过解析后的
        save_path: 保存路径
        raw_data: 原始json数据
        csv_path: csv文件保存路径，用于记录下载状态
    """
    # 如果原始文件为None，则设置为空字典
    raw_data = raw_data if raw_data else {}

    try:
        title = note_info.get('title', '')
        if not title:
            desc = note_info.get('desc', '').replace('\n', '')
            if len(desc) > 10:
                title = desc[:10] + "..."
            else:
                title = desc if desc else note_info.get('note_id', 'unknown')
            note_info['title'] = title

        # 规范化标题，处理特殊字符
        title = norm_str(title)
        note_id = note_info.get('note_id', 'unknown')

        # 下载时将用户昵称作为文件夹的一部分
        nickname = norm_str(note_info.get('nickname', '未知'))
        user_id = note_info.get('user_id', 'unknown')
        note_type = note_info.get('note_type', '')

        # 首先检查是否已下载完成(csv中标记为完成)
        if check_download_status(note_info, save_path, csv_path):
            logger.debug(f"笔记 {note_id} 已完整下载，跳过")
            return None

        # 创建保存目录
        local_path = f"{save_path}/{nickname}_{user_id}/{title}_{note_id}"
        os.makedirs(local_path, exist_ok=True)

        # 使用笔记类型决定下载行为
        start_time = time.time()
        success = True

        # 检查哪些文件已存在，只下载缺失的部分
        if note_type == '视频':
            video_url = note_info.get('video_addr', None)
            video_path = f"{local_path}/video.mp4"
            
            # 检查视频文件是否存在
            video_exists = os.path.exists(video_path) and os.path.getsize(video_path) > 0
            # 检查是否为全新下载
            is_new_download = not os.path.exists(local_path) or len(os.listdir(local_path)) <= 1
            
            if video_url and not video_exists:
                if is_new_download:
                    logger.info(f"↓ 视频笔记 [{title}_{note_id}] (作者: {nickname}) 开始全新下载")
                else:
                    logger.info(f"↓ 视频笔记 [{title}_{note_id}] (作者: {nickname}) 开始下载视频")
                # 只下载视频
                success = download_video(video_url, local_path)
            elif video_url and video_exists:
                logger.info(f"视频笔记 [{title}_{note_id}] 视频已存在，跳过下载")
                success = True
            else:
                logger.error(f"视频笔记 [{title}_{note_id}] 未找到视频地址")
                success = False

        elif note_type == '图集' or note_type == '图集视频':
            # 图集类型，检查并下载缺失的图片
            image_list = note_info.get('image_list', [])
            if image_list:
                # 是否包含视频
                has_videos = note_type == '图集视频' and 'live_videos_list' in note_info and note_info['live_videos_list']
                log_type = "图集视频" if has_videos else "图集"
                
                # 检查目录是否已存在，用于判断是全新下载还是更新下载
                is_new_download = not os.path.exists(local_path) or len(os.listdir(local_path)) <= 1  # 只有目录或只有info.json
                
                # 收集缺失的图片索引
                missing_images = []
                for i in range(len(image_list)):
                    img_path = f"{local_path}/image_{i}.jpg"
                    if not os.path.exists(img_path) or os.path.getsize(img_path) == 0:
                        missing_images.append(i)
                
                # 下载缺失的图片
                if missing_images:
                    if is_new_download:
                        logger.info(f"↓ {log_type}笔记 [{title}_{note_id}] (作者: {nickname}) 开始全新下载")
                        logger.info(f"  下载全部 {len(missing_images)} 张图片")
                    else:
                        logger.info(f"↓ {log_type}笔记 [{title}_{note_id}] (作者: {nickname}) 下载缺失图片")
                        logger.info(f"  下载{len(missing_images)}张缺失图片，索引: {missing_images}")
                    for i in missing_images:
                        if i < len(image_list):  # 确保索引有效
                            img_url = image_list[i]
                            file_path = f"{local_path}/image_{i}.jpg"
                            download_success = download_file(img_url, file_path, 'image')
                            success = download_success and success
                else:
                    logger.info(f"{log_type}笔记 [{title}_{note_id}] 所有图片已存在，无需下载")

                # 下载视频(如果有)
                if has_videos:
                    live_videos = note_info['live_videos_list']
                    # 确保 live_videos 是列表
                    if not isinstance(live_videos, list):
                        if isinstance(live_videos, str):
                            live_videos = [live_videos]
                        else:
                            logger.warning(f"不支持的视频格式: {type(live_videos)}")
                            live_videos = []

                    # 获取视频和图片的映射关系
                    video_image_mapping = {}
                    if isinstance(note_info.get('video_image_mapping'), dict):
                        video_image_mapping = note_info.get('video_image_mapping')
                    
                    # 收集缺失的视频
                    missing_videos = []
                    for i, video_url in enumerate(live_videos):
                        # 确定视频对应的图片索引
                        img_idx = i  # 默认使用序号
                        for vid_key, mapped_idx in video_image_mapping.items():
                            if (str(i) == str(vid_key) or 
                                f"video_{i}" == str(vid_key) or 
                                str(i) in str(vid_key)):
                                img_idx = mapped_idx
                                break
                        
                        # 检查视频文件是否存在
                        video_filename = f"live_video_{img_idx}.mp4"
                        video_path = f"{local_path}/{video_filename}"
                        if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
                            missing_videos.append((i, img_idx, video_url))
                    
                    # 下载缺失的视频
                    if missing_videos:
                        # 如果不是全新下载，才显示下载缺失视频的信息
                        if not is_new_download:
                            logger.info(f"  下载{len(missing_videos)}个缺失视频")
                        else:
                            logger.info(f"  下载全部 {len(missing_videos)} 个视频")
                        
                        for i, img_idx, video_url in missing_videos:
                            if not isinstance(video_url, str):
                                logger.warning(f"跳过非字符串URL: {video_url}")
                                continue
                                
                            try:
                                video_filename = f"live_video_{img_idx}.mp4"
                                video_success = download_video(video_url, local_path, video_filename)
                                success = video_success and success
                                
                                # 记录视频与图片的对应关系
                                if video_success:
                                    video_image_mapping[f"video_{i}"] = img_idx
                            except Exception as video_error:
                                logger.error(f"下载视频 {i} 时出错: {video_error}")
                                success = False
                                
                        # 更新笔记信息中的视频映射关系
                        note_info['video_image_mapping'] = video_image_mapping
                    else:
                        logger.info(f"{log_type}笔记 [{title}_{note_id}] 所有视频已存在，无需下载")
            
            else:
                logger.error(f"图集笔记 [{title}_{note_id}] 未找到图片列表")
                success = False
        
        # 将信息和原始数据保存到本地
        with open(f"{local_path}/info.json", "w", encoding="utf-8") as f:
            json.dump(note_info, f, ensure_ascii=False, indent=2)
            
        with open(f"{local_path}/raw_data.json", "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)
            
        # 计算下载耗时
        time_cost = time.time() - start_time
        
        # 更新CSV记录的下载状态
        if csv_path:
            update_download_status(note_id, user_id, success, csv_path)
            
        # 下载完成提示
        if success:
            logger.info(f"✓ {note_type}笔记 [{title}_{note_id}] (作者: {nickname}) 下载完成")
        else:
            logger.error(f"✗ {note_type}笔记 [{title}_{note_id}] (作者: {nickname}) 下载失败")
        
        return local_path
    except Exception as e:
        logger.error(f"下载笔记时出现错误: {e}")
        logger.debug(f"错误详情: {traceback.format_exc()}")
        return None

def update_download_status(note_id, user_id, status, csv_path):
    """
    更新下载状态到CSV记录
    
    :param note_id: 笔记ID
    :param user_id: 用户ID
    :param status: 下载状态(True/False)
    :param csv_path: CSV文件路径
    """
    if not csv_path:
        return
        
    try:
        import os
        import csv
        
        # 检查CSV文件
        csv_file = os.path.join(csv_path, f"{user_id}_download_record.csv")
        if not os.path.exists(csv_file):
            logger.warning(f"CSV文件不存在: {csv_file}")
            return
            
        # 读取现有记录
        rows = []
        found = False
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            # 更新状态
            for i, row in enumerate(rows):
                if i > 0 and row and row[0] == note_id:
                    # 更新is_complete字段
                    if len(row) > 6:
                        row[6] = str(status)
                    else:
                        # 确保行有足够的列
                        while len(row) < 7:
                            row.append("")
                        row[6] = str(status)
                    rows[i] = row
                    found = True
                    break
        
        # 如果没有找到记录
        if not found:
            logger.warning(f"未找到笔记记录: {note_id}")
            return
            
        # 写回更新后的记录
        with open(csv_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
            
    except Exception as e:
        logger.error(f"更新下载状态失败: {e}")
        
def check_download_status(note_id, user_id, csv_path):
    """
    检查笔记是否已完成下载
    
    :param note_id: 笔记ID
    :param user_id: 用户ID
    :param csv_path: CSV文件路径
    :return: 是否已完成下载
    """
    if not csv_path:
        return False
        
    try:
        import os
        import csv
        
        # 检查CSV文件
        csv_file = os.path.join(csv_path, f"{user_id}_download_record.csv")
        if not os.path.exists(csv_file):
            return False
            
        # 读取记录
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # 跳过表头
            for row in reader:
                if row and row[0] == note_id:
                    # 检查是否完成
                    if len(row) > 6 and row[6].strip().lower() == 'true':
                        # 如果记录为已完成，还需要检查文件是否真实存在
                        return True
        
        # 未找到记录或记录为未完成
        return False
        
    except Exception as e:
        logger.warning(f"检查下载状态失败: {e}")
        return False

def check_and_create_path(path):
    if not os.path.exists(path):
        os.makedirs(path)
