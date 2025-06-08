import os
from datetime import datetime, time
from loguru import logger
from xhs_utils.common_utils import load_env

# 加载环境变量
load_env()

class ScheduleController:
    """
    时间段控制器，用于判断当前时间是否在允许爬取的时间段内
    """
    def __init__(self):
        # 读取配置
        self.enabled = os.getenv('SCHEDULE_ENABLED', 'false').lower() == 'true'
        self.mode = os.getenv('SCHEDULE_MODE', 'allowlist')
        self.time_ranges_str = os.getenv('SCHEDULE_TIMES', '')
        
        # 解析时间段
        self.time_ranges = []
        if self.time_ranges_str:
            try:
                for time_range_str in self.time_ranges_str.split(';'):
                    if '-' not in time_range_str:
                        continue
                    start_str, end_str = time_range_str.split('-')
                    start_time = self._parse_time(start_str)
                    end_time = self._parse_time(end_str)
                    if start_time and end_time:
                        self.time_ranges.append((start_time, end_time))
                        
                if self.enabled and self.time_ranges:
                    ranges_str = ', '.join([f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}" 
                                          for start, end in self.time_ranges])
                    mode_desc = "允许" if self.mode == 'allowlist' else "禁止"
                    logger.info(f"时间段控制已启用，模式：{mode_desc}爬取，时间段：{ranges_str}")
                elif self.enabled and not self.time_ranges:
                    logger.warning("时间段控制已启用，但未设置有效的时间段，将使用默认行为（全天爬取）")
                    self.enabled = False
            except Exception as e:
                logger.error(f"解析时间段配置出错: {e}")
                self.enabled = False
    
    def _parse_time(self, time_str):
        """
        解析时间字符串为time对象
        :param time_str: 格式为HH:MM的时间字符串
        :return: time对象
        """
        try:
            hour, minute = map(int, time_str.strip().split(':'))
            return time(hour=hour, minute=minute)
        except Exception as e:
            logger.error(f"时间格式错误 '{time_str}': {e}")
            return None
    
    def is_time_allowed(self):
        """
        判断当前时间是否允许爬取
        :return: 如果当前时间允许爬取则返回True，否则返回False
        """
        # 如果未启用时间段控制，则始终允许爬取
        if not self.enabled:
            return True
        
        # 如果没有设置时间段，也始终允许爬取
        if not self.time_ranges:
            return True
        
        # 获取当前时间
        now = datetime.now().time()
        
        # 检查当前时间是否在任何时间段内
        in_any_range = any(start <= now <= end for start, end in self.time_ranges)
        
        # 根据模式返回结果
        if self.mode == 'allowlist':
            # 白名单模式：只在指定时间段内爬取
            return in_any_range
        else:
            # 黑名单模式：在指定时间段内不爬取
            return not in_any_range
    
    def get_next_allowed_time(self):
        """
        获取下一个允许爬取的时间
        :return: 下一个允许爬取的时间描述，如果总是允许则返回None
        """
        if not self.enabled or not self.time_ranges:
            return None
            
        now = datetime.now()
        current_time = now.time()
        
        if self.mode == 'allowlist':
            # 白名单模式：找到下一个允许的开始时间
            for start, end in sorted(self.time_ranges):
                if current_time < start:
                    next_time = datetime.combine(now.date(), start)
                    return f"{next_time.strftime('%H:%M')}"
            
            # 如果今天没有更多时间段，则找明天的第一个时间段
            first_start = min(start for start, _ in self.time_ranges)
            next_time = datetime.combine(now.date(), first_start)
            next_time = next_time.replace(day=next_time.day + 1)
            return f"明天 {next_time.strftime('%H:%M')}"
            
        else:
            # 黑名单模式：找到当前禁止时间段的结束时间
            for start, end in sorted(self.time_ranges):
                if start <= current_time <= end:
                    next_time = datetime.combine(now.date(), end)
                    return f"{next_time.strftime('%H:%M')}"
            
            # 如果当前不在任何禁止时间段内，则返回None
            return None

# 创建全局实例
schedule_controller = ScheduleController() 