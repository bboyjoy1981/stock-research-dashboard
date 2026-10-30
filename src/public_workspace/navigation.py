"""Validated public navigation, isolated by trusted entry-point namespace."""
import re


class PublicNavigation:
    def __init__(self,namespace,allowed_pages,state):
        if namespace not in ('owner','guest'):
            raise ValueError('Untrusted navigation namespace')
        self.namespace=namespace
        self.allowed_pages=tuple(allowed_pages)
        self.state=state

    def _set(self,values):
        for key,value in values.items():
            self.state[f'{self.namespace}_{key}']=value
        return True

    def open_page(self,page):
        if not isinstance(page,str) or page not in self.allowed_pages:
            return False
        return self._set({'page':page})

    def open_stock(self,code,allowed_codes,industry=None,parent=None):
        if '个股详情' not in self.allowed_pages or not isinstance(code,str) or not re.fullmatch(r'[0-9]{6}',code) or code not in allowed_codes:
            return False
        if any(value is not None and (not isinstance(value,str) or not value.strip()) for value in (industry,parent)):
            return False
        return self._set({'code':code,'page':'个股详情','stock_industry':industry,'stock_parent':parent})

    def focus_sector(self,field,value,allowed_pairs,parent=None):
        if '大盘云图' not in self.allowed_pages or field not in ('行业','细分行业','板块') or not isinstance(value,str):
            return False
        if parent is None:
            matches={p for p,c in allowed_pairs if c==value}
            if len(matches)!=1:
                return False
            parent=next(iter(matches))
        if not isinstance(parent,str) or (parent,value) not in allowed_pairs:
            return False
        revision=self.state.get(f'{self.namespace}_sector_revision',0)
        if type(revision) is not int or revision<0: revision=0
        return self._set({'page':'大盘云图','sector_field':field,'sector_parent':parent,'sector':value,
                          'sector_revision':revision+1})
