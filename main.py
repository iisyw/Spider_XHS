import os
from loguru import logger
from apis.pc_apis import XHS_Apis
from xhs_utils.common_utils import init, load_env, load_user_urls
from xhs_utils.data_util import handle_note_info, download_note, save_to_xlsx, create_note_record, norm_str, check_note_files_complete
from xhs_utils.push_util import pusher
import sys
import csv
import random
import time
from datetime import datetime, timedelta
import json

# 配置日志级别为DEBUG，显示所有调试信息
logger.remove()
logger.add(sink=sys.stderr, level="INFO")

class Data_Spider():
    def __init__(self):
        self.xhs_apis = XHS_Apis()

    def spider_note(self, note_url: str, cookies_str: str, proxies=None):
        """
        爬取一个笔记的信息
        :param note_url:
        :param cookies_str:
        :return:
        """
        note_info = None
        raw_data = None
        try:
            success, msg, response_data = self.xhs_apis.get_note_info(note_url, cookies_str, proxies)
            if success:
                raw_data = response_data  # 保存原始数据
                note_info = response_data['data']['items'][0]
                note_info['url'] = note_url
                note_info = handle_note_info(note_info)
                
                # 在这里添加对笔记类型的识别处理
                note_type = note_info.get('note_type', '')
                
                # 如果note_type不存在或为空，基于图片和视频判断类型
                if not note_type:
                    has_images = note_info.get('image_list') and len(note_info.get('image_list')) > 0
                    has_video = note_info.get('video_addr') and note_info.get('video_addr') != 'None'
                    has_live_videos = note_info.get('live_videos_list') and len(note_info.get('live_videos_list')) > 0
                    
                    if has_live_videos:
                        note_info['note_type'] = '图集视频'
                    elif has_video:
                        note_info['note_type'] = '视频'
                    elif has_images:
                        note_info['note_type'] = '图集'
                    else:
                        note_info['note_type'] = '未知类型'
                # 确保类型名称正确(历史兼容性处理)
                elif note_type == '图文':
                    note_info['note_type'] = '图集'
                
        except Exception as e:
            success = False
            msg = e
            # 发送推送通知，爬取笔记失败
            pusher.notify_error("爬取笔记失败", f"笔记URL: {note_url}\n错误信息: {msg}")
        logger.info(f'爬取笔记信息 {note_url}: {success}, msg: {msg}')
        return success, msg, note_info, raw_data

    def spider_some_note(self, notes: list, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None, user_name="未知", pre_fetched_notes=None):
        """
        爬取一些笔记的信息
        :param notes: 笔记URL列表
        :param cookies_str: cookies字符串
        :param base_path: 保存路径
        :param save_choice: 保存选择
        :param excel_name: Excel名称
        :param proxies: 代理
        :param user_name: 用户名称或搜索关键词，用于结果通知
        :param pre_fetched_notes: 已经获取过详细信息的笔记字典，格式为 {note_url: (note_info, raw_data)}
        :return:
        """
        if (save_choice == 'all' or save_choice == 'excel') and excel_name == '':
            raise ValueError('excel_name 不能为空')
        note_list = []
        failed_notes = []  # 存储下载失败的笔记
        raw_data_dict = {}  # 存储每个笔记的原始数据
        
        # 初始化预获取笔记字典
        pre_fetched_notes = pre_fetched_notes or {}
        
        # 开始下载前记录总笔记数
        total_notes = len(notes)
        if total_notes == 0:
            logger.info(f"没有找到需要下载的笔记")
            return [], []
            
        # 先检查本地文件完整性，只对不完整的笔记发起API请求
        needs_api_request = []  # 需要发起API请求的笔记
        for note_url in notes:
            # 从URL中提取笔记ID
            note_id = note_url.split('/')[-1].split('?')[0]
            
            # 检查是否已在预获取列表中
            if note_url in pre_fetched_notes:
                # 已经获取过详情的笔记，直接使用缓存
                note_info, raw_data = pre_fetched_notes[note_url]
                note_list.append(note_info)
                raw_data_dict[note_info['note_id']] = raw_data
                continue
                
            # 检查CSV记录和本地文件完整性
            is_complete = check_note_files_complete(note_id, base_path.get('csv'), base_path.get('media'))
            
            if is_complete:
                logger.debug(f"笔记 {note_id} 本地文件完整，跳过API请求")
                # 尝试从本地加载笔记信息
                try:
                    user_id = None
                    # 查找对应的CSV文件
                    csv_path = base_path.get('csv')
                    if csv_path:
                        import glob
                        # 搜索可能包含此笔记的CSV文件
                        for csv_file in glob.glob(os.path.join(csv_path, '*_download_record.csv')):
                            try:
                                with open(csv_file, 'r', encoding='utf-8') as f:
                                    reader = csv.reader(f)
                                    next(reader)  # 跳过表头
                                    for row in reader:
                                        if row and row[0] == note_id:
                                            user_id = os.path.basename(csv_file).replace('_download_record.csv', '')
                                            break
                                    if user_id:
                                        break
                            except Exception as e:
                                logger.warning(f"读取CSV文件错误 {csv_file}: {e}")
                    
                    if user_id:
                        # 尝试加载info.json
                        nickname = "未知用户"  # 默认昵称
                        title = note_id  # 默认使用ID作为标题
                        
                        # 遍历用户文件夹寻找对应笔记
                        media_path = base_path.get('media')
                        if media_path and os.path.exists(media_path):
                            for user_folder in os.listdir(media_path):
                                if user_folder.endswith(f"_{user_id}"):
                                    user_dir = os.path.join(media_path, user_folder)
                                    # 查找包含note_id的文件夹
                                    for note_folder in os.listdir(user_dir):
                                        if note_id in note_folder and os.path.isdir(os.path.join(user_dir, note_folder)):
                                            note_dir = os.path.join(user_dir, note_folder)
                                            info_path = os.path.join(note_dir, 'info.json')
                                            if os.path.exists(info_path):
                                                with open(info_path, 'r', encoding='utf-8') as f:
                                                    note_info = json.load(f)
                                                    note_list.append(note_info)
                                                    logger.debug(f"从本地加载笔记 {note_id} 详细信息")
                                                    break
                    
                    # 如果未能从本地加载，仍需API请求
                    if note_id not in [note.get('note_id') for note in note_list if note]:
                        needs_api_request.append(note_url)
                except Exception as e:
                    logger.warning(f"尝试从本地加载笔记 {note_id} 信息失败: {e}")
                    needs_api_request.append(note_url)
            else:
                # 文件不完整，需要API请求
                needs_api_request.append(note_url)
        
        # 对需要API请求的笔记进行爬取
        actually_downloaded_count = 0
        api_request_count = len(needs_api_request)
        
        if api_request_count > 0:
            logger.info(f"总共 {total_notes} 个笔记，需要API请求的数量: {api_request_count}")
            
            for note_url in needs_api_request:
                try:
                    # 进行API请求获取笔记详情
                    success, msg, note_info, raw_data = self.spider_note(note_url, cookies_str, proxies)
                    
                    if note_info is not None and success:
                        note_list.append(note_info)
                        if raw_data:
                            raw_data_dict[note_info['note_id']] = raw_data
                    else:
                        # 记录下载失败的笔记
                        failed_note = {
                            'note_url': note_url,
                            'error': msg if isinstance(msg, str) else str(msg)
                        }
                        failed_notes.append(failed_note)
                except Exception as e:
                    logger.error(f"处理笔记 {note_url} 时发生异常: {e}")
                    failed_notes.append({
                        'note_url': note_url,
                        'error': str(e)
                    })
        
        # 处理下载成功的笔记
        for note_info in note_list:
            if not note_info:
                continue
                
            note_id = note_info.get('note_id')
            if not note_id:
                continue
                
            if save_choice == 'all' or save_choice == 'media':
                raw_data = raw_data_dict.get(note_id)
                
                # 检查是否已存在且完整
                is_complete = check_note_files_complete(note_id, base_path.get('csv'), base_path.get('media'))
                
                # 如果已完成，则记录跳过；否则进行下载并增加计数
                if is_complete:
                    logger.debug(f"笔记 {note_id} 已完整下载，跳过")
                else:
                    download_note(note_info, base_path['media'], raw_data, base_path.get('csv'))
                    actually_downloaded_count += 1
        
        # 保存到Excel
        if save_choice == 'all' or save_choice == 'excel':
            try:
                file_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}.xlsx'))
                save_to_xlsx(note_list, file_path)
            except Exception as e:
                logger.error(f"保存Excel时发生错误: {e}")
        
        # 只有在实际下载了新内容或有失败记录时才发送通知
        if actually_downloaded_count > 0 or failed_notes:
            logger.info(f"实际下载了 {actually_downloaded_count} 个笔记，失败 {len(failed_notes)} 个")
            pusher.notify_download_results(user_name, total_notes, len(note_list), failed_notes)
        else:
            logger.info(f"所有笔记都已下载完成，无需重复下载，跳过通知")
            
        return note_list, failed_notes


    def spider_user_all_note(self, user_url: str, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None):
        """
        爬取一个用户的所有笔记
        :param user_url:
        :param cookies_str:
        :param base_path:
        :return:
        """
        note_list = []
        new_note_list = []  # 新增笔记列表，用于推送通知
        user_id = None
        nickname = "未知用户"
        
        try:
            # 从URL中提取用户ID
            user_id = user_url.split('/')[-1].split('?')[0]
            
            # 尝试获取用户信息
            try:
                success, msg, user_info = self.xhs_apis.get_user_info(user_id, cookies_str, proxies)
                if success and 'data' in user_info and 'basic_info' in user_info['data']:
                    nickname = user_info['data']['basic_info'].get('nickname', "未知用户")
            except Exception as e:
                logger.warning(f"获取用户信息失败: {e}")
            
            # 获取笔记列表
            success, msg, all_note_info = self.xhs_apis.get_user_all_notes(user_url, cookies_str, proxies)
            if success:
                logger.info(f'用户 {nickname}({user_id}) 作品数量: {len(all_note_info)}')
                
                # 读取已下载记录
                csv_path = base_path.get('csv')
                existing_notes = set()
                existing_notes_info = {}  # 存储已下载笔记的信息
                if csv_path and user_id:
                    csv_file = os.path.join(csv_path, f'{user_id}_download_record.csv')
                    if os.path.exists(csv_file):
                        with open(csv_file, 'r', encoding='utf-8') as f:
                            reader = csv.reader(f)
                            next(reader)  # 跳过表头
                            for row in reader:
                                if row and len(row) > 0:
                                    note_id = row[0]
                                    existing_notes.add(note_id)  # 添加note_id
                                    # 存储笔记的标题、类型和描述等信息
                                    if len(row) >= 7:  # 确保行包含所有必要字段
                                        existing_notes_info[note_id] = {
                                            'title': row[3],  # title在第4列
                                            'note_type': row[2],  # note_type在第3列
                                            'desc': row[4],  # desc在第5列
                                        }
                
                # 收集笔记和潜在的新笔记
                potential_new_notes = []  # 潜在新笔记的ID和URL
                for simple_note_info in all_note_info:
                    note_id = simple_note_info['note_id']
                    note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={simple_note_info['xsec_token']}"
                    note_list.append(note_url)
                    
                    # 检查是否为新笔记
                    if note_id not in existing_notes:
                        potential_new_notes.append({
                            'note_id': note_id, 
                            'note_url': note_url,
                            'user_id': user_id
                        })
                
                # 只对新笔记发起API请求
                confirmed_new_notes = []
                pre_fetched_notes = {}  # 保存已获取的笔记详细信息
                
                if potential_new_notes:
                    logger.info(f"发现{len(potential_new_notes)}篇潜在新笔记，获取详细信息...")
                    for new_note in potential_new_notes:
                        note_id = new_note['note_id']
                        note_url = new_note['note_url']
                        
                        try:
                            # 获取完整的笔记信息
                            success, msg, note_info, raw_data = self.spider_note(note_url, cookies_str, proxies)
                            if success and note_info:
                                # 缓存已获取的详细信息
                                pre_fetched_notes[note_url] = (note_info, raw_data)
                                
                                # 使用详细信息创建CSV记录
                                is_existing, _ = create_note_record(note_info, base_path.get('csv'))
                                if not is_existing:
                                    # 添加到确认的新笔记列表
                                    confirmed_new_notes.append(note_info)
                                    logger.debug(f"确认新笔记: ID={note_id}, 标题='{note_info['title']}', 类型='{note_info['note_type']}', 描述='{note_info['desc']}'")
                            else:
                                logger.warning(f"获取笔记 {note_id} 详细信息失败: {msg}")
                        except Exception as e:
                            logger.warning(f"处理新笔记 {note_id} 时出错: {e}")
                    
                    # 推送新笔记通知
                    if confirmed_new_notes:
                        pusher.notify_new_notes(nickname, confirmed_new_notes)
                        logger.info(f"确认{len(confirmed_new_notes)}篇新笔记，已推送通知")
                    else:
                        logger.info(f"没有发现新笔记，跳过推送通知")
                
                # 下载所有笔记（包括旧笔记）
                if save_choice == 'all' or save_choice == 'excel':
                    excel_name = user_url.split('/')[-1].split('?')[0]
                self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, proxies, nickname, pre_fetched_notes)
            else:
                # 推送错误通知
                if "登录" in msg or "cookie" in str(msg).lower():
                    pusher.notify_error("Cookies失效", f"用户: {nickname}({user_id})\n错误信息: {msg}")
                else:
                    pusher.notify_error("爬取用户笔记失败", f"用户: {nickname}({user_id})\n错误信息: {msg}")
        except Exception as e:
            success = False
            msg = e
            # 推送错误通知
            error_msg = f"用户: {nickname}"
            if user_id:
                error_msg += f"({user_id})"
            error_msg += f"\n错误信息: {e}"
            pusher.notify_error("爬虫异常", error_msg)
            
        logger.info(f'爬取用户所有笔记 {user_url}: {success}, msg: {msg}')
        return note_list, success, msg


    def spider_some_search_note(self, query: str, require_num: int, cookies_str: str, base_path: dict, save_choice: str, sort="general", note_type=0,  excel_name: str = '', proxies=None):
        """
            指定数量搜索笔记，设置排序方式和笔记类型和笔记数量
            :param query 搜索的关键词
            :param require_num 搜索的数量
            :param cookies_str 你的cookies
            :param base_path 保存路径
            :param sort 排序方式 general:综合排序, time_descending:时间排序, popularity_descending:热度排序
            :param note_type 笔记类型 0:全部, 1:视频, 2:图文
            返回搜索的结果
        """
        note_list = []
        new_note_list = []  # 新增笔记列表
        try:
            success, msg, notes = self.xhs_apis.search_some_note(query, require_num, cookies_str, sort, note_type, proxies)
            if success:
                notes = list(filter(lambda x: x['model_type'] == "note", notes))
                logger.info(f'搜索关键词 {query} 笔记数量: {len(notes)}')
                
                # 读取已下载记录
                existing_notes = set()
                existing_notes_info = {}  # 存储已下载笔记信息
                csv_path = base_path.get('csv')
                if csv_path:
                    import glob
                    import csv
                    # 搜索可能涉及多个用户，需要检查所有CSV记录
                    for csv_file in glob.glob(os.path.join(csv_path, '*_download_record.csv')):
                        try:
                            with open(csv_file, 'r', encoding='utf-8') as f:
                                reader = csv.reader(f)
                                next(reader)  # 跳过表头
                                for row in reader:
                                    if row and len(row) > 0:
                                        note_id = row[0]
                                        existing_notes.add(note_id)  # 添加note_id
                                        if len(row) >= 7:  # 确保行包含所有必要字段
                                            existing_notes_info[note_id] = {
                                                'title': row[3],  # title在第4列
                                                'note_type': row[2],  # note_type在第3列
                                                'desc': row[4],  # desc在第5列
                                            }
                        except Exception as e:
                            logger.warning(f"读取CSV文件错误 {csv_file}: {e}")
                
                # 收集潜在的新笔记
                potential_new_notes = []  # 潜在新笔记的ID和URL
                for note in notes:
                    note_id = note['id']
                    note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={note['xsec_token']}"
                    note_list.append(note_url)
                    
                    # 检查是否为新笔记
                    if note_id not in existing_notes:
                        potential_new_notes.append({
                            'note_id': note_id,
                            'note_url': note_url
                        })
                
                # 只对新笔记发起API请求
                confirmed_new_notes = []
                pre_fetched_notes = {}  # 保存已获取的笔记详细信息
                
                if potential_new_notes:
                    logger.info(f"发现{len(potential_new_notes)}篇潜在搜索结果笔记，获取详细信息...")
                    for new_note in potential_new_notes:
                        note_id = new_note['note_id']
                        note_url = new_note['note_url']
                        
                        try:
                            # 获取完整的笔记信息
                            success, msg, note_info, raw_data = self.spider_note(note_url, cookies_str, proxies)
                            if success and note_info:
                                # 缓存已获取的详细信息
                                pre_fetched_notes[note_url] = (note_info, raw_data)
                                
                                # 使用详细信息创建CSV记录
                                is_existing, _ = create_note_record(note_info, base_path.get('csv'))
                                if not is_existing:
                                    # 添加到确认的新笔记列表
                                    confirmed_new_notes.append(note_info)
                                    logger.debug(f"确认搜索笔记: ID={note_id}, 标题='{note_info['title']}', 类型='{note_info['note_type']}', 描述='{note_info['desc']}'")
                            else:
                                logger.warning(f"获取搜索笔记 {note_id} 详细信息失败: {msg}")
                        except Exception as e:
                            logger.warning(f"处理搜索笔记 {note_id} 时出错: {e}")
                    
                    # 推送新笔记通知
                    if confirmed_new_notes:
                        pusher.notify_new_notes(f"搜索: {query}", confirmed_new_notes)
                        logger.info(f"搜索关键词'{query}'发现{len(confirmed_new_notes)}篇新笔记，已推送通知")
                    else:
                        logger.info(f"搜索关键词'{query}'没有发现新笔记，跳过推送通知")
                
                # 下载所有笔记（包括旧笔记）
                if save_choice == 'all' or save_choice == 'excel':
                    excel_name = query
                self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, proxies, f"搜索: {query}", pre_fetched_notes)
            else:
                # 推送错误通知
                if "登录" in msg or "cookie" in str(msg).lower():
                    pusher.notify_error("Cookies失效", f"搜索关键词: {query}\n错误信息: {msg}")
                else:
                    pusher.notify_error("搜索笔记失败", f"搜索关键词: {query}\n错误信息: {msg}")
        except Exception as e:
            success = False
            msg = e
            # 推送错误通知
            pusher.notify_error("搜索笔记异常", f"搜索关键词: {query}\n错误信息: {e}")
            
        logger.info(f'搜索关键词 {query} 笔记: {success}, msg: {msg}')
        return note_list, success, msg

if __name__ == '__main__':
    """
        此文件为爬虫的入口文件，可以直接运行
        apis/pc_apis.py 为爬虫的api文件，包含小红书的全部数据接口，可以继续封装，感谢star和follow
    """
    # 发送启动通知
    pusher.notify_startup()
    logger.info("爬虫程序已启动，已发送通知")
    
    # 初始化基本路径和数据爬虫
    cookies_str, base_path = init()
    data_spider = Data_Spider()
    
    # 读取运行模式配置
    run_mode = os.environ.get('RUN_MODE', 'continuous').strip().lower()
    logger.info(f"爬虫运行模式: {run_mode}")
    
    # 记录初始加载的配置信息
    user_urls = load_user_urls()
    if user_urls:
        logger.info(f"初始加载了 {len(user_urls)} 个用户URL")
    else:
        logger.warning("未配置要爬取的用户URL，请在.env文件中设置USER_URLS，爬虫将在配置后开始工作")
    
    # 监听循环处理用户
    def process_users_with_interval(user_urls, cookies_str, base_path):
        """
        循环处理用户URL列表，每次处理完一个用户后随机等待30~60秒
        :param user_urls: 要爬取的用户URL列表
        :param cookies_str: cookies字符串
        :param base_path: 保存路径
        """
        if not user_urls:
            logger.warning("用户URL列表为空，无法处理")
            return
            
        for i, user_url in enumerate(user_urls):
            # 提取用户ID用于日志
            user_id = user_url.split('/')[-1].split('?')[0]
            logger.info(f"开始处理用户 {i+1}/{len(user_urls)}: {user_id}")
            
            try:
                # 爬取该用户的所有笔记
                note_list, success, msg = data_spider.spider_user_all_note(user_url, cookies_str, base_path, 'all')
                
                # 统计本次用户处理结果
                if success:
                    logger.info(f"用户 {user_id} 爬取完成，共检查 {len(note_list)} 篇笔记")
                else:
                    logger.warning(f"用户 {user_id} 爬取出现问题: {msg}")
                
                # 如果不是最后一个用户，等待随机时间
                if i < len(user_urls) - 1:
                    # 随机等待时间（30-60秒）
                    wait_seconds = random.randint(30, 60)
                    logger.info(f"等待 {wait_seconds} 秒后继续下一个用户")
                    time.sleep(wait_seconds)
                    logger.info("等待结束，开始下一个用户")
            except Exception as e:
                logger.error(f"处理用户 {user_id} 时出错: {e}")
                pusher.notify_error("爬虫错误", f"处理用户 {user_id} 时出错: {e}")
                
                # 即使出错，也等待一段时间再继续
                if i < len(user_urls) - 1:
                    wait_seconds = random.randint(20, 40)  # 出错后等待稍短一些
                    logger.info(f"出错后等待 {wait_seconds} 秒后继续")
                    time.sleep(wait_seconds)
        
        # 所有用户处理完成
        logger.info(f"所有 {len(user_urls)} 个用户处理完成")
        # 只运行一次模式下，发送完成通知
        if run_mode == 'once':
            pusher.notify_info("爬取完成", f"一次性运行模式已完成，共处理 {len(user_urls)} 个用户")

    # 开始连续监听处理
    def continuous_monitoring(base_path):
        """
        持续监听处理，每次处理完所有用户后等待1-2小时
        :param base_path: 保存路径
        """
        cycle_count = 0  # 周期计数
        
        while True:
            try:
                # 每轮循环开始时重新读取环境变量，获取最新的cookies和用户URL列表
                current_cookies = load_env()
                current_user_urls = load_user_urls()
                
                # 如果没有URL可爬取，等待后重试
                if not current_user_urls:
                    logger.warning("没有配置任何要爬取的用户URL，本轮循环将跳过")
                    wait_minutes = 30  # 如果没有URL，减少等待时间
                    logger.info(f"等待 {wait_minutes} 分钟后重新检查配置...")
                    time.sleep(wait_minutes * 60)
                    continue  # 跳过本轮循环
                
                # 记录当前轮次开始时间
                cycle_count += 1
                cycle_start_time = datetime.now()
                logger.info(f"开始第 {cycle_count} 轮爬取周期，时间: {cycle_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"已重新加载环境变量配置，当前监控 {len(current_user_urls)} 个用户")
                pusher.notify_info("开始新周期", f"开始第 {cycle_count} 轮爬取周期，时间: {cycle_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n将爬取 {len(current_user_urls)} 个用户")
                
                # 处理所有用户，使用最新读取的cookies和用户列表
                process_users_with_interval(current_user_urls, current_cookies, base_path)
                
                # 计算本轮用时
                cycle_end_time = datetime.now()
                duration_minutes = (cycle_end_time - cycle_start_time).total_seconds() / 60
                
                # 随机等待时间（1-2小时）
                wait_minutes = random.randint(60, 120)
                wait_seconds = wait_minutes * 60
                
                # 计算等待结束时间
                next_start_time = cycle_end_time + timedelta(minutes=wait_minutes)
                
                # 记录等待信息
                logger.info(f"第 {cycle_count} 轮爬取完成，用时 {duration_minutes:.1f} 分钟")
                logger.info(f"等待 {wait_minutes} 分钟后开始第 {cycle_count + 1} 轮 (将在 {next_start_time.strftime('%Y-%m-%d %H:%M:%S')} 继续)")
                
                # 只有在第一轮或者每5轮发送一次休息通知，避免通知过多
                if cycle_count == 1 or cycle_count % 5 == 0:
                    pusher.notify_info("周期休息", f"第 {cycle_count} 轮爬取完成，用时 {duration_minutes:.1f} 分钟\n休息 {wait_minutes} 分钟后，将于 {next_start_time.strftime('%Y-%m-%d %H:%M:%S')} 开始第 {cycle_count + 1} 轮爬取")
                
                # 等待指定时间
                time.sleep(wait_seconds)
                
            except Exception as e:
                # 处理整个周期的异常，休息后继续
                logger.error(f"第 {cycle_count} 轮周期处理中出现错误: {e}")
                pusher.notify_error("周期错误", f"第 {cycle_count} 轮爬取周期执行出错: {e}\n系统将在30分钟后尝试重新开始")
                
                # 出错后等待30分钟
                time.sleep(30 * 60)
    
    # 根据运行模式选择执行方式
    if run_mode == 'once':
        # 一次性运行模式
        logger.info("启动一次性运行模式，将处理所有用户后退出")
        process_users_with_interval(user_urls, cookies_str, base_path)
        logger.info("一次性运行模式完成，程序退出")
    else:
        # 持续监听模式（默认）
        logger.info("启动持续监听模式，将循环处理所有用户")
        continuous_monitoring(base_path)
    
    # 注释掉原来的代码
    # save_choice: all: 保存所有的信息, media: 保存视频和图片, excel: 保存到excel
    # save_choice 为 excel 或者 all 时，excel_name 不能为空
    # 1 - 爬取指定笔记
    # notes = [
    #     r'https://www.xiaohongshu.com/explore/67d7c713000000000900e391?xsec_token=AB1ACxbo5cevHxV_bWibTmK8R1DDz0NnAW1PbFZLABXtE=&xsec_source=pc_user',
    # ]
    # data_spider.spider_some_note(notes, cookies_str, base_path, 'all', 'test')

    # 2 - 爬取用户所有笔记
    # user_url = 'https://www.xiaohongshu.com/user/profile/67a332a2000000000d008358?xsec_token=ABTf9yz4cLHhTycIlksF0jOi1yIZgfcaQ6IXNNGdKJ8xg=&xsec_source=pc_feed'
    # data_spider.spider_user_all_note(user_url, cookies_str, base_path, 'all')

    # 3 - 关键词搜索爬取
    # query = "榴莲"
    # query_num = 10
    # sort = "general"
    # note_type = 0
    # data_spider.spider_some_search_note(query, query_num, cookies_str, base_path, 'all', sort, note_type)
