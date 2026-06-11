from app.services.indexing.keyword_indexer import _terms


def test_terms_extracts_searchable_chinese_keyphrases():
    terms = _terms("审计署2024年度授予中小企业合同金额和占比是多少？")

    assert "审计署" in terms
    assert "2024" in terms
    assert "中小企业" in terms
    assert "合同金额" in terms
    assert "占比" in terms
    assert all("是多少" not in term for term in terms)


def test_terms_extracts_procurement_standard_phrases():
    terms = _terms("数据库政府采购需求标准中，数据检索增强功能是否包括中文检索？")

    assert "数据库" in terms
    assert "政府采购" in terms
    assert "需求标准" in terms
    assert "数据检索" in terms
    assert "增强功能" in terms
    assert "中文检索" in terms
