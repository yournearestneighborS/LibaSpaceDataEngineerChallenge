"""Company spiders backed by :mod:`SmartRecruitersBase`."""

from jobs.spiders.SmartRecruitersBase import SmartRecruitersBase


class VisaSpider(SmartRecruitersBase):
    name = "VisaSmartRecruiters"
    company_name = "Visa"
    company_identifier = "Visa"
    start_url = "https://api.smartrecruiters.com/v1/companies/Visa/postings"
    start_urls = [start_url]


class BoschGroupSpider(SmartRecruitersBase):
    name = "BoschGroupSmartRecruiters"
    company_name = "Bosch Group"
    company_identifier = "BoschGroup"
    start_url = "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings"
    start_urls = [start_url]


class SmartRecruitersSpider(SmartRecruitersBase):
    name = "SmartRecruiters"
    company_name = "SmartRecruiters"
    company_identifier = "smartrecruiters"
    start_url = "https://api.smartrecruiters.com/v1/companies/smartrecruiters/postings"
    start_urls = [start_url]

