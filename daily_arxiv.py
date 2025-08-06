import sys
import os

# 添加本地库路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

import os
import re
import json
import arxiv
import yaml
import logging
import argparse
import datetime

print(arxiv.__file__)  # 应该显示来自lib/arxiv的路径


logging.basicConfig(format='[%(asctime)s %(levelname)s] %(message)s',
                    datefmt='%m/%d/%Y %H:%M:%S',
                    level=logging.INFO)

def load_config(config_file:str) -> dict:
    '''
    config_file: input config file path
    return: a dict of configuration
    '''"http://arxiv.org/"
    # make filters pretty
    def pretty_filters(**config) -> dict:
        keywords = dict()
        OR = 'OR'
        def parse_filters(filters:list):
            ret = ''
            for idx in range(0,len(filters)):
                filter = filters[idx]
                ret += (f'"{filter}"')  # 统一格式
                if idx != len(filters) - 1:
                    ret += f" {OR} "  # 注意前后空格
            return ret
        for k,v in config['keywords'].items():
            keywords[k] = parse_filters(v['filters'])
        return keywords
    with open(config_file,'r') as f:
        config = yaml.load(f,Loader=yaml.FullLoader)
        config['kv'] = pretty_filters(**config)  # 处理配置文件中 keywords 字段的内容
        logging.info(f'config = {config}')
    return config

def get_authors(authors, first_author = False):
    output = str()
    if first_author == False:
        output = ", ".join(str(author) for author in authors)
    else:
        output = authors[0]
    return output
def sort_papers(papers):
    # Sort by date, which is the first element in the markdown table row
    # The value of papers is a string like:
    # "|**2024-06-07**|**Title**|Author et.al.|[2406.04843](http://arxiv.org/abs/2406.04843)|null|\n"
    try:
        sorted_items = sorted(papers.items(), key=lambda item: item[1].split('|')[1].strip().replace('**', ''), reverse=True)
        return dict(sorted_items)
    except IndexError:
        # Fallback for old format or error
        logging.warning("Could not sort papers by date. Using old sorting method.")
        output = dict()
        keys = list(papers.keys())
        keys.sort(reverse=True)
        for key in keys:
            output[key] = papers[key]
        return output

def get_daily_papers(topic,query="slam", max_results=2):
    """
    @param topic: str
    @param query: str
    @return paper_with_code: dict
    """
    # output
    content = dict()
    content_to_web = dict()

    # # 设置时间范围（格式：YYYYMMDD）
    # start_date = "20240501"
    # end_date = "20240931"
    #
    # # 构造查询字符串，包含关键词和时间范围
    # query = f'"flow matching" AND submittedDate:[{start_date} TO {end_date}]'

    search_engine = arxiv.Search(
        query = query,
        max_results = max_results,
        sort_by = arxiv.SortCriterion.SubmittedDate
    )

    for result in search_engine.results():

        paper_id            = result.get_short_id()
        paper_title         = result.title
        paper_first_author  = get_authors(result.authors,first_author = True)
        update_time         = result.updated.date()
        comments            = result.comment

        logging.info(f"Time = {update_time} title = {paper_title} author = {paper_first_author}")

        # eg: 2108.09112v1 -> 2108.09112
        ver_pos = paper_id.find('v')
        if ver_pos == -1:
            paper_key = paper_id
        else:
            paper_key = paper_id[0:ver_pos]
        paper_url = "http://arxiv.org/" + 'abs/' + paper_key

        content[paper_key] = "|**{}**|**{}**|{} et.al.|[{}]({})|null|\n".format(
               update_time,paper_title,paper_first_author,paper_key,paper_url)
        content_to_web[paper_key] = "- {}, **{}**, {} et.al., Paper: [{}]({})".format(
               update_time,paper_title,paper_first_author,paper_url,paper_url)

        # TODO: select useful comments
        if comments != None:
            content_to_web[paper_key] += f", {comments}\n"
        else:
            content_to_web[paper_key] += f"\n"



    data = {topic:content}
    data_web = {topic:content_to_web}
    return data,data_web

def update_json_file(filename,data_dict):
    '''
    daily update json file using data_dict
    更新JSON文件：update_json_file函数将新获取的论文数据合并到已有的JSON文件中（按主题组织）。
    '''
    with open(filename,"r") as f:
        content = f.read()
        if not content:
            m = {}
        else:
            m = json.loads(content)

    json_data = m.copy()

    # update papers in each keywords         
    for data in data_dict:
        for keyword in data.keys():
            papers = data[keyword]

            if keyword in json_data.keys():
                json_data[keyword].update(papers)
            else:
                json_data[keyword] = papers

    with open(filename,"w") as f:
        json.dump(json_data,f)

def json_to_md(tts_arxiv_daily_json, readme_md,
               task = '',
               to_web = False,
               use_title = True,
               use_tc = True,
               show_badge = True,
               use_b2t = True):
    """
    核心方法

    转换JSON到Markdown：json_to_md函数将JSON数据转换为格式化的Markdown表格，
    并支持生成GitHub Pages页面（包括目录、返回顶部链接等）。
    """
    def pretty_math(s:str) -> str:
        ret = ''
        match = re.search(r"\$.*\$", s)
        if match == None:
            return s
        math_start,math_end = match.span()
        space_trail = space_leading = ''
        if s[:math_start][-1] != ' ' and '*' != s[:math_start][-1]: space_trail = ' '
        if s[math_end:][0] != ' ' and '*' != s[math_end:][0]: space_leading = ' '
        ret += s[:math_start]
        ret += f'{space_trail}${match.group()[1:-1].strip()}${space_leading}'
        ret += s[math_end:]
        return ret

    DateNow = datetime.date.today()
    DateNow = str(DateNow)
    DateNow = DateNow.replace('-','.')

    with open(tts_arxiv_daily_json, "r") as f:
        content = f.read()
        if not content:
            data = {}
        else:
            data = json.loads(content)

    # 清空原始的readme.md文档的内容
    with open(readme_md, "w+") as f:
        pass

    # write data into README.md      # 文件打开后，读写位置处于文件末尾。新写入的数据会添加到文件原有内容的后面。
    with open(readme_md, "a+") as f: # a+模式 写入行为：该模式不会清空原文件内容，若文件不存在，同样会创建新文件。

        if use_title == True:
            f.write("## Updated on " + DateNow + "\n")
        else:
            f.write("> Updated on " + DateNow + "\n")

        # TODO: add usage
        f.write("> Usage instructions: [here](./docs/README.md#usage)\n\n")
        f.write("> This page is modified from [here](https://github.com/Vincentqyw/cv-arxiv-daily)\n\n")

        #Add: table of contents
        if use_tc == True: # use_tc: 布尔值，控制是否生成目录（Table of Contents）。
            f.write("<details>\n")
            f.write("  <summary>Table of Contents</summary>\n")
            f.write("  <ol>\n")
            for keyword in data.keys():
                day_content = data[keyword]
                if not day_content:
                    continue
                kw = keyword.replace(' ','-')
                f.write(f"    <li><a href=#{kw.lower()}>{keyword}</a></li>\n")
            f.write("  </ol>\n")
            f.write("</details>\n\n")

        for keyword in data.keys():
            day_content = data[keyword] # day_content 是以日期为Key 论文标题等信息为值的字典
            if not day_content:
                continue
            # the head of each part
            f.write(f"## {keyword}\n\n")

            if use_title == True :
                if to_web == False:
                    f.write("|Publish Date|Title|Authors|PDF|Code|\n" + "|---|---|---|---|---|\n")
                else:
                    f.write("| Publish Date | Title | Authors | PDF | Code |\n")
                    f.write("|:---------|:-----------------------|:---------|:------|:------|\n")

            # sort papers by date
            day_content = sort_papers(day_content)

            for _,v in day_content.items():
                if v is not None:
                    f.write(pretty_math(v)) # make latex pretty

            f.write(f"\n")

            #Add: back to top
            if use_b2t:  # use_b2t: 布尔值，控制是否在每个部分后面添加“返回顶部”的链接。
                top_info = f"#Updated on {DateNow}"
                top_info = top_info.replace(' ','-').replace('.','')
                f.write(f"<p align=right>(<a href={top_info.lower()}>back to top</a>)</p>\n\n")

    logging.info(f"{task} finished")

def demo(**config):
    data_collector = []
    data_collector_web= []
    keywords = config['kv']
    max_results = config['max_results']
    logging.info(f"GET daily papers begin")
    for topic, keyword in keywords.items():
        logging.info(f"Keyword: {topic}")
        data, data_web = get_daily_papers(topic, query = keyword, max_results = max_results)
        data_collector.append(data)
        data_collector_web.append(data_web)
        print("\n")
    logging.info(f"GET daily papers end")
    # 1. update README.md file
    tts_arxiv_daily_json = config['json_readme_path']
    readme_md   = config['md_readme_path']
    # update json data
    update_json_file(tts_arxiv_daily_json,data_collector)
    # json data to markdown
    json_to_md(tts_arxiv_daily_json,readme_md, task ='Update Readme')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_path',type=str, default='config.yaml',
                            help='configuration file path')
    args = parser.parse_args()
    config = load_config(args.config_path)
    config = {**config}
    demo(**config)
