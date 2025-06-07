<p align="center">
  <a href="https://github.com/cv-cat/Spider_XHS" target="_blank" align="center" alt="Go to XHS_Spider Website">
    <picture>
      <img width="220" src="https://github.com/user-attachments/assets/b817a5d2-4ca6-49e9-b7b1-efb07a4fb325" alt="Spider_XHS logo">
    </picture>
  </a>
</p>


<div align="center">
    <a href="https://www.python.org/">
        <img src="https://img.shields.io/badge/python-3.7%2B-blue" alt="Python 3.7+">
    </a>
    <a href="https://nodejs.org/zh-cn/">
        <img src="https://img.shields.io/badge/nodejs-18%2B-blue" alt="NodeJS 18+">
    </a>
</div>



# Spider_XHS

**✨ 专业的小红书数据采集解决方案，支持笔记爬取，保存格式为excel或者media**

**✨ 小红书全域运营解决方法，AI一键改写笔记（图文，视频）直接上传**

**✨ 支持持续监控模式，自动检测并下载最新内容，推送通知实时提醒**

## ⭐功能列表

**⚠️ 任何涉及数据注入的操作都是不被允许的，本项目仅供学习交流使用，如有违反，后果自负**

| 模块       | 已实现                                                                             |
|----------|---------------------------------------------------------------------------------|
| 小红书创作者平台 | ✅ 二维码登录<br/>✅ 手机验证码登录<br/>✅ 上传（图集、视频）作品<br/>✅查看自己上传的作品      |
| 小红书PC    | ✅ 二维码登录<br/> ✅ 手机验证码登录<br/> ✅ 获取无水印图片<br/> ✅ 获取无水印视频<br/> ✅ 获取主页的所有频道<br/>✅ 获取主页推荐笔记<br/>✅ 获取某个用户的信息<br/>✅ 用户自己的信息<br/>✅ 获取某个用户上传的笔记<br/>✅ 获取某个用户所有的喜欢笔记<br/>✅ 获取某个用户所有的收藏笔记<br/>✅ 获取某个笔记的详细内容<br/>✅ 搜索笔记内容<br/>✅ 搜索用户内容<br/>✅ 获取某个笔记的评论<br/>✅ 获取未读消息信息<br/>✅ 获取收到的评论和@提醒信息<br/>✅ 获取收到的点赞和收藏信息<br/>✅ 获取新增关注信息|
| 监控与通知    | ✅ 持续监控用户笔记更新<br/> ✅ 新内容检测与下载<br/> ✅ 文件完整性检查<br/> ✅ PushDeer推送通知<br/> ✅ 环境变量动态加载 |


## 🌟 功能特性

- ✅ **多维度数据采集**
  - 用户主页信息
  - 笔记详细内容
  - 智能搜索结果抓取
- 🚀 **高性能架构**
  - 自动重试机制
  - 增量下载（仅下载新内容）
  - 文件完整性检查
- 🔔 **实时通知**
  - 爬虫启动通知
  - 新笔记发现提醒
  - 下载结果统计
  - 错误异常告警
- 🔄 **持续监控**
  - 定时轮询检查
  - 环境变量动态加载
  - 配置热更新（无需重启）
- 🔒 **安全稳定**
  - 小红书最新API适配
  - 异常处理机制
  - proxy代理
- 🎨 **便捷管理**
  - 结构化目录存储
  - 格式化输出（JSON/EXCEL/MEDIA）
  
## 🎨效果图
### 处理后的所有用户
![image](https://github.com/cv-cat/Spider_XHS/assets/94289429/00902dbd-4da1-45bc-90bb-19f5856a04ad)
### 某个用户所有的笔记
![image](https://github.com/cv-cat/Spider_XHS/assets/94289429/880884e8-4a1d-4dc1-a4dc-e168dd0e9896)
### 某个笔记具体的内容
![image](https://github.com/cv-cat/Spider_XHS/assets/94289429/d17f3f4e-cd44-4d3a-b9f6-d880da626cc8)
### 保存的excel
![image](https://github.com/user-attachments/assets/707f20ed-be27-4482-89b3-a5863bc360e7)

## 🛠️ 快速开始
### ⛳运行环境
- Python 3.7+
- Node.js 18+

### 🎯安装依赖
```
pip install -r requirements.txt
npm install
```

### 🐳 Docker部署
项目支持Docker容器化部署，提供两种部署方式：

#### 1. 使用Docker Compose（推荐）
```bash
# 克隆项目
git clone https://github.com/your-username/Spider_XHS.git
cd Spider_XHS

# 创建并编辑.env配置文件
cp .env.example .env  # 如果没有.env.example，请手动创建.env文件
vi .env               # 编辑配置文件，填入必要的配置项

# 使用Docker Compose启动服务
docker-compose up -d

# 查看日志
docker logs -f spider_xhs
```

#### 2. 使用Docker直接构建运行
```bash
# 构建镜像
docker build -t spider_xhs .

# 运行容器
docker run -d --name spider_xhs \
  -v $(pwd)/datas:/app/datas \
  -v $(pwd)/.env:/app/.env \
  -e TZ=Asia/Shanghai \
  spider_xhs
```

**Docker部署优势:**
- 环境隔离，避免依赖冲突
- 持久化存储，自动挂载数据目录
- 支持热更新配置文件（修改.env后自动生效）
- 容器自动重启策略(always)，保障长时间稳定运行
- 采用国内镜像源，加速构建过程

### 🎨配置文件
配置文件在项目根目录`.env`文件中，包含以下配置项：

#### 1. COOKIES配置（必需）

将小红书登录cookie放入其中，cookie获取方法：在浏览器中按F12打开控制台，点击网络(Network)标签，找到任意一个接口请求，查看其Cookie信息。

![image](https://github.com/user-attachments/assets/6a7e4ecb-0432-4581-890a-577e0eae463d)

**注意：必须是登录小红书后的cookie才有效！**

#### 2. PUSHDEER_KEY配置（可选）

用于接收爬虫运行状态的推送通知，包括：
- 爬虫启动通知
- 发现新笔记提醒
- 下载完成统计
- 错误和异常提醒

PushDeer是一个开源的推送服务，支持iOS、Android、Web等多平台。[点此获取PushDeer](https://www.pushdeer.com/)。

#### 3. USER_URLS配置（必需）

设置要监控的用户URL列表，多个URL使用分号(;)分隔：

```
# .env文件示例
# 小红书登录凭证，用于API认证
COOKIES='你的cookie字符串'

# PushDeer推送服务密钥，用于发送爬虫状态通知
PUSHDEER_KEY='你的PushDeer密钥'

# 要爬取的用户URL列表，使用分号(;)分隔多个URL
USER_URLS='https://www.xiaohongshu.com/user/profile/用户ID1?xsec_token=xxx;https://www.xiaohongshu.com/user/profile/用户ID2?xsec_token=yyy'

# 爬虫运行模式：once(运行一次后退出)或continuous(持续监听模式)
RUN_MODE='continuous'

# 持续监听模式下每轮的等待间隔时间范围（分钟）
MONITORING_INTERVAL_MIN='60'  # 最小等待时间，默认60分钟
MONITORING_INTERVAL_MAX='120' # 最大等待时间，默认120分钟(2小时)

# 用户爬取间隔时间范围（秒）
USER_INTERVAL_MIN='30'  # 最小等待时间，默认30秒
USER_INTERVAL_MAX='60'  # 最大等待时间，默认60秒

# 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL='INFO'
```

**重要提示：在爬虫运行过程中，可以直接修改`.env`文件中的配置，无需重启程序，下一轮循环会自动加载最新配置。这包括Cookies、监控用户URL列表、等待时间间隔以及日志级别等所有配置项。**

### 🚀运行项目
```
python main.py
```

### 🔄 持续监控模式

项目默认以持续监控模式运行，会定期检查指定用户的新笔记并下载：

1. 每轮检查所有配置的用户
2. 对每个用户，检测是否有新发布的笔记
3. 发现新笔记时，通过PushDeer推送通知
4. 下载新内容并保存文件
5. 每轮结束后，等待1-2小时后进行下一轮检查

**特性：**
- 自动记录已下载内容，避免重复下载
- 检查文件完整性，确保内容完整无缺失
- 配置热更新，无需重启程序即可更改监控目标
- 灵活的错误处理机制，确保长时间稳定运行

### 🗝️注意事项
- main.py中的代码是爬虫的入口，可以根据自己的需求进行修改
- apis/pc_apis.py中的代码包含了所有的api接口，可以根据自己的需求进行修改
- 媒体文件（图片/视频）保存在datas/media_datas目录下
- Excel文件保存在datas/excel_datas目录下
- CSV记录（用于增量下载）保存在datas/csv_datas目录下


## 🍥日志
   
| 日期       | 说明                          |
|----------| --------------------------- |
| 23/08/09 | - 首次提交 |
| 23/09/13 | - api更改params增加两个字段，修复图片无法下载，有些页面无法访问导致报错 |
| 23/09/16 | - 较大视频出现编码问题，修复视频编码问题，加入异常处理 |
| 23/09/18 | - 代码重构，加入失败重试 |
| 23/09/19 | - 新增下载搜索结果功能 |
| 23/10/05 | - 新增跳过已下载功能，获取更详细的笔记和用户信息|
| 23/10/08 | - 上传代码☞Pypi，可通过pip install安装本项目|
| 23/10/17 | - 搜索下载新增排序方式选项（1、综合排序 2、热门排序 3、最新排序）|
| 23/10/21 | - 新增图形化界面,上传至release v2.1.0|
| 23/10/28 | - Fix Bug 修复搜索功能出现的隐藏问题|
| 25/03/18 | - 更新API，修复部分问题|
| 25/06/05 | - 增加对live_photo带视频的图集类型识别和处理 |
| 25/06/05 | - 新增文件完整性检查，确保下载内容完整无缺失 |
| 25/06/05 | - 集成PushDeer推送通知功能，实时提醒爬虫运行状态 |
| 25/06/06 | - 新增环境变量配置系统，支持动态加载用户URL列表和Cookies |
| 25/06/06 | - 优化持续监控模式，实现配置热更新（无需重启程序） |
| 25/06/06 | - 完善docker的使用 |
| 25/06/07 | - 优化文件检查逻辑，减少API请求次数，提高爬取效率 |
| 25/06/07 | - 调整CSV记录格式，改进换行处理，增加图片和视频数量统计 |
| 25/06/07 | - 增加运行模式配置，可选择运行一次或持续监听模式 |
| 25/07/27 | - 新增持续监控间隔时间配置，支持自定义最小和最大等待时间 |


## 🧸额外说明
1. 感谢star⭐和follow📰！不时更新
2. 作者的联系方式在主页里，有问题可以随时联系我
3. 可以关注下作者的其他项目，欢迎 PR 和 issue
4. 感谢赞助！如果此项目对您有帮助，请作者喝一杯奶茶~~ （开心一整天😊😊）
5. thank you~~~

<div align="center">
  <h3>原作者收款码</h3>
  <img src="./author/wx_pay.png" width="400px" alt="微信赞赏码"> 
  <img src="./author/zfb_pay.jpg" width="400px" alt="支付宝收款码">
</div>

<div align="center">
  <h3>二次开发者收款码</h3>
  <p>如果您觉得新增的持续监控、推送通知、环境变量配置等功能对您有帮助，也可以支持二次开发者</p>
  <!-- 这里替换为您自己的收款码图片路径和alt文本 -->
  <img src="./two_anthor/wx_pay.jpg" width="400px" alt="二次开发者微信收款码"> 
  <img src="./two_anthor/zfb_pay.jpg" width="400px" alt="二次开发者支付宝收款码">
</div>


## 📈 Star 趋势
<a href="https://www.star-history.com/#cv-cat/Spider_XHS&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=cv-cat/Spider_XHS&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=cv-cat/Spider_XHS&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=cv-cat/Spider_XHS&type=Date" />
 </picture>
</a>


