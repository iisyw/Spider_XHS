import requests
import platform
import socket
from datetime import datetime
from loguru import logger
import re

class PushDeer:
    def __init__(self, pushkey):
        """
        初始化PushDeer推送工具
        :param pushkey: PushDeer的推送密钥
        """
        self.pushkey = pushkey
        self.api_url = "https://api2.pushdeer.com/message/push"
    
    def send_message(self, title, content, type="markdown"):
        """
        发送推送消息
        :param title: 消息标题
        :param content: 消息内容
        :param type: 内容类型，可选text或markdown
        :return: 是否推送成功
        """
        try:
            payload = {
                "pushkey": self.pushkey,
                "text": title,
                "desp": content,
                "type": type
            }
            response = requests.post(self.api_url, data=payload)
            result = response.json()
            
            if result.get("code") == 0:
                logger.info(f"消息推送成功: {title}")
                return True
            else:
                logger.error(f"消息推送失败: {result}")
                return False
        except Exception as e:
            logger.error(f"消息推送异常: {e}")
            return False
    
    def notify_startup(self):
        """
        通知爬虫启动
        :return: 是否推送成功
        """
        # 获取主机名和IP地址
        hostname = socket.gethostname()
        try:
            ip_address = socket.gethostbyname(hostname)
        except:
            ip_address = "未知"
            
        # 获取操作系统信息
        os_info = platform.platform()
        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        title = "🚀 小红书爬虫已启动"
        content = f"### 爬虫启动通知\n\n" \
                  f"- **启动时间**: {start_time}\n" \
                  f"- **主机名**: {hostname}\n" \
                  f"- **IP地址**: {ip_address}\n" \
                  f"- **系统环境**: {os_info}\n\n" \
                  f"爬虫程序已成功启动，开始监控数据。"
        
        return self.send_message(title, content)
    
    def notify_new_notes(self, user_name, new_notes):
        """
        通知有新的笔记
        :param user_name: 用户名称
        :param new_notes: 新笔记列表，每个元素为字典，包含note_id, title, url等信息
        :return: 是否推送成功
        """
        title = f"🔔 爬虫监控：{user_name}有新笔记"
        content = f"### 发现{len(new_notes)}篇新笔记\n\n"
        
        for i, note in enumerate(new_notes[:10]):  # 最多显示10篇
            # 获取基本信息，确保使用正确的字段
            # 记录接收到的完整笔记对象，帮助调试
            logger.debug(f"处理第{i+1}个推送笔记: {note}")
            
            title_text = note.get('title', '无标题')
            note_type = note.get('note_type', '未知类型')
            note_url = note.get('note_url', '')
            desc = note.get('desc', '')
            
            # 从描述中提取简短预览，保留话题标签
            desc_brief = ''
            if desc:
                # 不再移除话题标签，直接使用原始描述，仅截取合适长度
                if len(desc) > 30:
                    desc_brief = desc[:30] + '...'
                else:
                    desc_brief = desc
            
            # 构造统一格式: 标题(类型)[描述前缀]
            display_text = f"{title_text}({note_type})"
            if desc_brief:
                display_text += f"[{desc_brief}]"
            
            # 记录日志
            logger.info(f"推送内容: 标题='{title_text}', 类型='{note_type}', 描述='{desc_brief}', 最终显示='{display_text}'")
            
            # 添加到推送内容
            content += f"{i+1}. [{display_text}]({note_url})\n"
        
        if len(new_notes) > 10:
            content += f"\n...等共{len(new_notes)}篇笔记"
        
        return self.send_message(title, content)
    
    def notify_download_results(self, user_name, total_notes, success_notes, failed_notes=None):
        """
        通知下载结果
        :param user_name: 用户名称或搜索关键词
        :param total_notes: 总笔记数量
        :param success_notes: 成功下载的笔记数量
        :param failed_notes: 失败的笔记列表，元素为字典，包含note_id, title, error等信息
        :return: 是否推送成功
        """
        if failed_notes is None:
            failed_notes = []
        
        success_rate = (success_notes / total_notes) * 100 if total_notes > 0 else 0
        title = f"📊 爬虫结果：{user_name}的笔记下载完成"
        
        content = f"### 下载结果统计\n\n" \
                  f"- **总计**: {total_notes}篇笔记\n" \
                  f"- **成功**: {success_notes}篇\n" \
                  f"- **失败**: {len(failed_notes)}篇\n" \
                  f"- **成功率**: {success_rate:.1f}%\n"
        
        if failed_notes:
            content += f"\n### 失败笔记列表\n\n"
            for i, note in enumerate(failed_notes[:5]):  # 最多显示5个失败笔记
                title_text = note.get('title', '无标题')
                error = note.get('error', '未知错误')
                content += f"{i+1}. {title_text}: {error}\n"
            
            if len(failed_notes) > 5:
                content += f"\n...等共{len(failed_notes)}篇笔记下载失败"
        
        return self.send_message(title, content)
    
    def notify_error(self, error_type, details):
        """
        通知爬虫遇到错误
        :param error_type: 错误类型（如"Cookies失效"）
        :param details: 错误详情
        :return: 是否推送成功
        """
        title = f"⚠️ 爬虫异常：{error_type}"
        content = f"### 错误详情\n\n{details}"
        
        return self.send_message(title, content)

# 初始化全局推送器实例
pusher = PushDeer("") 