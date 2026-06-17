import os
import re
import smtplib
import json
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# 配置常量
URL = "https://www.nifdc.org.cn/nifdc/bshff/bzhwzh/bzwztzgg/index.html"
RECEIVER = "1065351139@qq.com"
LOG_FILE = "send_log.json"

CN_NUM = {'一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10, '百':100}

def cn_to_an(cn):
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
    smtp_server = "smtp.qq.com"
    port = 465
    sender = os.environ.get("EMAIL_USERNAME")
    password = os.environ.get("EMAIL_PASSWORD")

    if not sender or not password:
        print("❌ 未配置邮箱环境变量（EMAIL_USERNAME 或 EMAIL_PASSWORD），取消发送邮件。")
        return False

    message = MIMEText(content, 'html', 'utf-8')
    message['From'] = formataddr((str(Header('中检院监控助手', 'utf-8')), sender))
    message['To'] = formataddr((str(Header('管理员', 'utf-8')), RECEIVER))
    message['Subject'] = Header(subject, 'utf-8')

    try:
        print(f"▶ 正在连接 SMTP 服务器 ({smtp_server}:{port}) 并尝试发送邮件...")
        server = smtplib.SMTP_SSL(smtp_server, port)
        server.login(sender, password)
        server.sendmail(sender, [RECEIVER], message.as_string())
        server.quit()
        print(f"💌 邮件发送成功：{subject}")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败，错误原因: {e}")
        return False

def main():
    print("▶ [步骤 1/4] 正在初始化脚本，读取历史发送日志...")
    history = {}
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
            print(f"成功加载历史日志文件，已记录 {len(history)} 条已发送公告。")
        except Exception as e:
            print(f"⚠ 读取日志文件失败（若为首次运行可忽略）: {e}")
    else:
        print("💡 未检测到历史日志文件，将作为首次运行处理。")

    print(f"▶ [步骤 2/4] 正在请求中检院目标网址: {URL}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(URL, headers=headers, timeout=20)
        response.encoding = 'utf-8'
        print(f"成功获取网页，HTTP 状态码: {response.status_code}，正在加载解析器...")
    except Exception as e:
        print(f"❌ 关键错误：请求中检院网页失败！可能是网络波动或网站拦截。错误详情: {e}")
        return

    print("▶ [步骤 3/4] 正在解析网页 HTML 内容并筛选目标链接...")
    soup = BeautifulSoup(response.text, 'html.parser')
    all_links = soup.find_all('a')
    print(f"网页解析完成，当前页面共包含 {len(all_links)} 个链接。")

    # 筛选包含关键词的公告
    links = [a for a in all_links if a.get_text() and "注册检验用体外诊断试剂国家标准品和参考品目录" in a.get_text()]
    print(f"经过标题关键词过滤，符合条件的目录通知共有: {len(links)} 个。")

    matched_notices = []

    for idx, link in enumerate(links, 1):
        title = link.get_text().strip()
        href = link.get('href', '')
        if href and not href.startswith('http'):
            href = "https://www.nifdc.org.cn" + href
        
        # 提取期数
        match = re.search(r"第([0-9一二三四五六七八九十]+)期", title)
        if match:
            stage_str = match.group(1)
            stage_num = cn_to_an(stage_str)
            print(f"  [{idx}] 发现目标公告: 【{title}】 -> 解析期数为: 第 {stage_num} 期")
            
            # 判断期数门槛
            if stage_num >= 17:
                if title not in history:
                    print(f"    📌 检测到未通知过的新公告，加入发送队列。")
                    matched_notices.append({"title": title, "url": href})
                else:
                    print(f"    (该公告此前已发送过通知，自动跳过)")
            else:
                print(f"    (期数低于第 17 期，不属于监控范围，跳过)")
        else:
            print(f"  [{idx}] 发现目标公告: 【{title}】，但未在标题中匹配到‘第X期’字样，跳过。")

    print("▶ [步骤 4/4] 正在进行最终结果判定...")
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if matched_notices:
        print(f"🚨 结果：本次运行共发现 {len(matched_notices)} 个新发布的目录通知！准备构建邮件...")
        email_content = "<h3>发现中检院新发布的相关目录通知：</h3><ul>"
        for notice in matched_notices:
            email_content += f'<li><a href="{notice["url"]}">{notice["title"]}</a></li>'
        email_content += "</ul>"
        
        # 升级为第 18 期提示语（可根据您的需要随时调整）
        subject = f"【中检院提示】发现第18期及以上体外诊断试剂标准品目录更新"
        
        if send_email(subject, email_content):
            # 发送成功后更新本地历史记录
            for notice in matched_notices:
                history[notice["title"]] = current_time_str
            
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=4)
            
            # 打印给 YAML 判断的特殊标识
            print("HAS_NEW_LOG=true")
            print("✅ 历史日志记录更新成功。")
    else:
        print("✅ 结果：本次运行未检测到任何需要通知的新期数。")

if __name__ == "__main__":
    main()
