from backend.app.services.activity import score_activity


def test_none_or_empty_unknown():
    assert score_activity(None) == -1
    assert score_activity("") == -1


def test_today_reply_count():
    assert score_activity("今日回复10+次") == 10
    assert score_activity("今日回复10次") == 10
    assert score_activity("今日回复9次") == 9
    assert score_activity("今日回复5次") == 5
    assert score_activity("今日回复3次") == 3


def test_qualitative_labels():
    assert score_activity("今日活跃") == 9
    assert score_activity("回复率高") == 8
    assert score_activity("简历处理快") == 7
    assert score_activity("喜欢聊天") == 6


def test_minutes_ago_reply():
    assert score_activity("1分钟前回复") == 10
    assert score_activity("2分钟前回复") == 9
    assert score_activity("3分钟前回复") == 8
    assert score_activity("4分钟前回复") == 8
    assert score_activity("5分钟前回复") == 7
    assert score_activity("6分钟前回复") == 7
    assert score_activity("7分钟前回复") == 6
    assert score_activity("10分钟前回复") == 5
    assert score_activity("20分钟前回复") == 0


def test_minutes_ago_resume():
    assert score_activity("1分钟前处理简历") == 10
    assert score_activity("5分钟前处理简历") == 7
    assert score_activity("7分钟前处理简历") == 6


def test_just_active():
    assert score_activity("刚刚活跃") == 10


def test_days_based():
    assert score_activity("1天内处理简历") == 10
    assert score_activity("7天内处理简历") == 4
    assert score_activity("1天") == 10
    assert score_activity("3天") == 8
    assert score_activity("7天") == 4
    assert score_activity("30天") == 1


def test_joined_takes_max():
    assert score_activity("今日回复10+次、简历处理快") == 10
    assert score_activity("回复率高、5分钟前处理简历") == 8
    assert score_activity("今日回复3次、喜欢聊天") == 6
    assert score_activity("简历处理快、今日活跃") == 9


def test_unknown_label_returns_unknown():
    assert score_activity("未知标签") == -1
    assert score_activity("简历处理快、未知标签") == 7
    assert score_activity("未知标签、再一个未知") == -1
