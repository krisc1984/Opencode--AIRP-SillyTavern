"""Tests for option extraction in handler.py."""

from __future__ import annotations

import pytest

from handler import extract_options


class TestExtractOptions:
    def test_options_block(self):
        text = "<options>\n> 去城市看看风景\n> 回村庄休息几天\n</options>"
        assert extract_options(text) == ["去城市看看风景", "回村庄休息几天"]

    def test_xx_block(self):
        text = "<xx>\n1. 去城市看看\n2. 回村庄休息\n</xx>"
        assert extract_options(text) == ["去城市看看", "回村庄休息"]

    def test_chinese_option_block_basic(self):
        text = (
            "<选项>\n"
            "<1>结束后把她拉进怀里<!--1-->\n"
            "<2>水龙头在哪儿？我去看看<!--2-->\n"
            "<3>系统弹窗：任务完成<!--3-->\n"
            "<4>胡姐，晚上我请你吃饭？<!--4-->\n"
            "<!--选项-->"
        )
        result = extract_options(text)
        assert result == [
            "结束后把她拉进怀里",
            "水龙头在哪儿？我去看看",
            "系统弹窗：任务完成",
            "胡姐，晚上我请你吃饭？",
        ]

    def test_chinese_option_block_with_html_tags(self):
        text = (
            "<选项>\n"
            '<1>把烟递给她，笑一下：<span class="speaking">那胡姐喜不喜欢小王八蛋？</span>——事后的调情确认<!--1-->\n'
            '<2><span class="speaking">你家的水龙头在哪儿？我去看看。</span>——用之前提过的借口收尾<!--2-->\n'
            "<!--选项-->"
        )
        result = extract_options(text)
        assert result == [
            '把烟递给她，笑一下：那胡姐喜不喜欢小王八蛋？——事后的调情确认',
            '你家的水龙头在哪儿？我去看看。——用之前提过的借口收尾',
        ]

    def test_chinese_option_block_truncates_to_five(self):
        text = (
            "<选项>\n"
            "<1>选项一很长<!--1-->\n"
            "<2>选项二也很长<!--2-->\n"
            "<3>选项三同样很长<!--3-->\n"
            "<4>选项四依然很长<!--4-->\n"
            "<5>选项五非常长<!--5-->\n"
            "<6>选项六极其长<!--6-->\n"
            "<!--选项-->"
        )
        result = extract_options(text)
        assert len(result) == 5
        assert result == ["选项一很长", "选项二也很长", "选项三同样很长", "选项四依然很长", "选项五非常长"]

    def test_chinese_option_block_empty_content_skipped(self):
        text = (
            "<选项>\n"
            "<1><!--1-->\n"
            "<2>有效选项内容<!--2-->\n"
            "<!--选项-->"
        )
        result = extract_options(text)
        assert result == ["有效选项内容"]

    def test_no_options_returns_empty(self):
        assert extract_options("") == []
        assert extract_options("没有选项的文本。") == []

    def test_options_block_takes_priority_over_chinese(self):
        text = (
            "<options>\n"
            "> 旧格式选项内容\n"
            "</options>\n"
            "<选项>\n"
            "<1>新格式选项内容<!--1-->\n"
            "<!--选项-->"
        )
        assert extract_options(text) == ["旧格式选项内容"]

    def test_chinese_option_block_without_closing_tag(self):
        # 如果没有 <!--选项--> 结束标签，不应解析
        text = "<选项>\n<1>orphan option<!--1-->\n"
        assert extract_options(text) == []
