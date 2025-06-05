import os
from loguru import logger
from apis.pc_apis import XHS_Apis
from xhs_utils.common_utils import init
from xhs_utils.data_util import handle_note_info, download_note, save_to_xlsx, create_note_record
from xhs_utils.push_util import pusher
import sys
import csv

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
            
        # 遍历下载笔记
        for note_url in notes:
            try:
                # 检查是否已经获取过该笔记的详细信息
                if note_url in pre_fetched_notes:
                    # 使用预获取的信息，避免重复请求API
                    note_info, raw_data = pre_fetched_notes[note_url]
                    success = True
                    msg = "使用预获取信息"
                    logger.debug(f"使用预获取笔记信息: {note_url}")
                else:
                    # 未获取过，请求API
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
        success_count = len(note_list)
        for note_info in note_list:
            if save_choice == 'all' or save_choice == 'media':
                raw_data = raw_data_dict.get(note_info['note_id'])
                download_note(note_info, base_path['media'], raw_data, base_path.get('csv'))
        
        # 保存到Excel
        if save_choice == 'all' or save_choice == 'excel':
            try:
                file_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}.xlsx'))
                save_to_xlsx(note_list, file_path)
            except Exception as e:
                logger.error(f"保存Excel时发生错误: {e}")
        
        # 推送下载结果通知
        if total_notes > 0:
            pusher.notify_download_results(user_name, total_notes, success_count, failed_notes)
            
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
                logger.info(f'用户 {user_url} 作品数量: {len(all_note_info)}')
                
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
                
                # 收集新笔记和所有笔记
                for simple_note_info in all_note_info:
                    note_id = simple_note_info['note_id']
                    note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={simple_note_info['xsec_token']}"
                    note_list.append(note_url)
                    
                    # 检查是否为新笔记，新笔记需要特殊处理
                    if note_id not in existing_notes:
                        # 收集潜在的新笔记的URL和初步信息，但暂不创建记录
                        logger.debug(f"发现潜在的新笔记: {note_id}")
                        new_note_list.append({
                            'note_id': note_id, 
                            'note_url': note_url,
                            'user_id': user_id
                        })
                
                # 优先处理新发现的笔记，先获取完整信息再创建记录和推送通知
                confirmed_new_notes = []
                pre_fetched_notes = {}  # 保存已获取的笔记详细信息
                if new_note_list:
                    logger.info(f"发现{len(new_note_list)}篇潜在新笔记，获取详细信息...")
                    for new_note in new_note_list:
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
                
                for note in notes:
                    note_id = note['id']
                    note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={note['xsec_token']}"
                    note_list.append(note_url)
                    
                    # 检查是否为新笔记，新笔记需要特殊处理
                    if note_id not in existing_notes:
                        # 收集潜在的新笔记的URL和初步信息
                        logger.debug(f"发现潜在的搜索笔记: {note_id}")
                        new_note_list.append({
                            'note_id': note_id,
                            'note_url': note_url
                        })
                
                # 优先处理新发现的笔记，先获取完整信息再创建记录和推送通知
                confirmed_new_notes = []
                pre_fetched_notes = {}  # 保存已获取的笔记详细信息
                if new_note_list:
                    logger.info(f"发现{len(new_note_list)}篇潜在搜索结果笔记，获取详细信息...")
                    for new_note in new_note_list:
                        note_id = new_note['note_id']
                        note_url = new_note['note_url']
                        
                        try:
                            # 获取完整的笔记信息
                            success, msg, note_info, raw_data = self.spider_note(note_url, cookies_str, proxies)
                            if success and note_info:
                                # 缓存已获取的详细信息
                                pre_fetched_notes[note_url] = (note_info, raw_data)
                                
                                # 获取用户ID，可能在note_info中已经包含
                                user_id = note_info.get('user_id', "search_results")
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
    
    cookies_str, base_path = init()
    data_spider = Data_Spider()
    # save_choice: all: 保存所有的信息, media: 保存视频和图片, excel: 保存到excel
    # save_choice 为 excel 或者 all 时，excel_name 不能为空
    # 1 - 爬取指定笔记
    notes = [
        r'https://www.xiaohongshu.com/explore/67d7c713000000000900e391?xsec_token=AB1ACxbo5cevHxV_bWibTmK8R1DDz0NnAW1PbFZLABXtE=&xsec_source=pc_user',
    ]
    data_spider.spider_some_note(notes, cookies_str, base_path, 'all', 'test')

    # 2 - 爬取用户所有笔记
    user_url = 'https://www.xiaohongshu.com/user/profile/67a332a2000000000d008358?xsec_token=ABTf9yz4cLHhTycIlksF0jOi1yIZgfcaQ6IXNNGdKJ8xg=&xsec_source=pc_feed'
    data_spider.spider_user_all_note(user_url, cookies_str, base_path, 'all')

    # 3 - 关键词搜索爬取
    query = "榴莲"
    query_num = 10
    sort = "general"
    note_type = 0
    data_spider.spider_some_search_note(query, query_num, cookies_str, base_path, 'all', sort, note_type)
