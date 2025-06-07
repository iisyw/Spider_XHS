import os
from loguru import logger
from dotenv import load_dotenv

def load_env():
    """
    从环境变量中加载配置信息
    :return: cookies字符串和日志级别
    """
    load_dotenv()
    cookies_str = os.getenv('COOKIES')
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    return cookies_str, log_level

def load_user_urls():
    """
    从环境变量中加载用户URL列表
    :return: 用户URL列表
    """
    load_dotenv()
    user_urls_str = os.getenv('USER_URLS', '')
    if not user_urls_str:
        logger.warning("环境变量中未设置USER_URLS，将使用空列表")
        return []
    
    # 使用分号分隔多个URL
    user_urls = [url.strip() for url in user_urls_str.split(';') if url.strip()]
    logger.info(f"从环境变量加载了 {len(user_urls)} 个用户URL")
    return user_urls

def init():
    media_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/media_datas'))
    excel_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/excel_datas'))
    csv_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/csv_datas'))
    for base_path in [media_base_path, excel_base_path, csv_base_path]:
        if not os.path.exists(base_path):
            os.makedirs(base_path)
            logger.info(f'创建目录 {base_path}')
    cookies_str, log_level = load_env()
    base_path = {
        'media': media_base_path,
        'excel': excel_base_path,
        'csv': csv_base_path,
    }
    return cookies_str, log_level, base_path
