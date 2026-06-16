import os
import re
import smtplib
import json
from email.mime.text import MIMEText
from email.header import Header
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# 配置常量
URL = "https://www.nifdc.org.cn/nifdc/bshff/bzhwzh/bzwztzgg/index.html"
RECEIVER = "1065351139@qq.com"
LOG_FILE = "send_log.json"

# 中文数字转阿拉伯数字映射
CN_NUM = {'一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10, '百':100}

def cn_to_an(cn):
    """简单将中文数字转为阿拉伯数字（支持百以内）"""
    if not cn: return 0
    if cn.isdigit(): return int(cn)
    val = 0
    if '十' in cn:
        idx = cn.index('十')
        left = cn[:idx]
        right = cn[idx+1:]
        val += (CN_NUM.get(left, 1) if left else 1) * 10
        if right: val += CN_NUM.get(right, 0)
    else:
        for c in cn: val += CN_NUM.get(c, 0)
    return val

def send_email(subject, content):
    """发送邮件"""
    smtp_server = "smtp.qq.com" # 如果你用QQ邮箱发，若是163请换成 smtp.163.com
    port = 465
    sender = os.environ.get("EMAIL_USERNAME")
    password = os.environ.get("EMAIL_PASSWORD")

    if not sender or not password:
        print("未配置邮箱环境变量，取消发送。")
        return False

    message = MIMEText(content, 'html', 'utf-8')
    message['From'] = Header(f"中检院监控助手 <{sender}>", 'utf-8')
    message['To'] = Header(RECEIVER, 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')

    try:
        server = smtplib.SMTP_SSL(smtp_server, port)
        server.login(sender, password)
        server.sendmail(sender, [RECEIVER], message.as_string())
        server.quit()
        print(f"邮件发送成功: {subject}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False

def main():
    # 1. 读取历史发送日志防止重复发送
    history = {}
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except:
            pass

    # 2. 请求网页
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        response.encoding = 'utf-8'
    except Exception as e:
        print(f"请求网页失败: {e}")
        return

    # 3. 解析网页内容
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 遍历页面所有超链接，筛选包含目标关键词的通知
    links = [a for a in soup.find_all('a') if a.get_text() and "注册检验用体外诊断试剂国家标准品和参考品目录" in a.get_text()]

    matched_notices = []

    for link in links:
        title = link.get_text().strip()
        href = link.get('href', '')
        if href and not href.startswith('http'):
            href = "https://www.nifdc.org.cn" + href
        
        # 提取期数
        match = re.search(r"第([0-9一二三四五六七八九十]+)期", title)
        if match:
            stage_str = match.group(1)
            stage_num = cn_to_an(stage_str)
            
            # 【测试调整】：只要大于等于 17 期就触发（可以匹配到现有的第十七期公告）
            if stage_num >= 17:
                # 【核心防重复逻辑】：如果这个标题在历史记录 (history) 中不存在，才加入发送列表
                if title not in history:
                    matched_notices.append({"title": title, "url": href})

    # 4. 如果有新满足条件的通知，发邮件并记录
    if matched_notices:
        email_content = "<h3>发现中检院新发布的相关目录通知（测试版）：</h3><ul>"
        for notice in matched_notices:
            email_content += f'<li><a href="{notice["url"]}">{notice["title"]}</a></li>'
        email_content += "</ul>"
        
        subject = f"【中检院监控测试】发现第17期及以上体外诊断试剂标准品目录更新"
        
        if send_email(subject, email_content):
            # 发送成功后，将这些标题写入历史日志
            for notice in matched_notices:
                history[notice["title"]] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=4)
            
            # 激活 GitHub Actions 的提交逻辑
            print("HAS_NEW_LOG=true")
    else:
        print("未检测到未通知的新期数，或者所有符合条件的通知均已发送过邮件。")

if __name__ == "__main__":
    main()
