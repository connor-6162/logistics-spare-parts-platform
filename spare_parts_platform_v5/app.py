from __future__ import annotations

import csv
import io
import os
import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta
from functools import wraps

import qrcode
from flask import (
    Flask,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, text
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-this-key"),
    SQLALCHEMY_DATABASE_URI=os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "spare_parts.db")
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=env_flag("SESSION_COOKIE_SECURE", False),
    PREFERRED_URL_SCHEME=os.environ.get("PREFERRED_URL_SCHEME", "http"),
)
DEMO_MODE = env_flag("DEMO_MODE", True)
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
APP_VERSION = "V5"
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "请先登录后继续操作"


ROLE_NAMES = {
    "admin": ("系统管理员", "System Administrator"),
    "worker": ("一线工人", "Frontline Worker"),
    "warehouse": ("仓库人员", "Warehouse Staff"),
    "maintenance": ("维修工程师", "Maintenance Engineer"),
    "procurement": ("采购人员", "Procurement Staff"),
    "manager": ("中层领导", "Middle Manager"),
    "executive": ("高层领导", "Executive"),
}

ROLE_PERMISSIONS = {
    "admin": {"*"},
    "worker": {"dashboard", "view_equipment", "view_parts", "view_faults", "report_fault"},
    "warehouse": {"dashboard", "view_parts", "manage_parts", "view_suppliers", "view_inbound", "manage_inbound", "view_stock", "manage_stock", "view_disposals", "manage_disposals", "export_data"},
    "maintenance": {"dashboard", "view_equipment", "view_parts", "view_stock", "view_faults", "report_fault", "process_fault", "view_lifecycle", "manage_lifecycle", "view_disposals", "manage_disposals", "export_data"},
    "procurement": {"dashboard", "view_parts", "view_suppliers", "manage_suppliers", "view_procurement", "create_procurement", "view_inbound", "export_data"},
    "manager": {"dashboard", "view_equipment", "view_parts", "view_suppliers", "view_procurement", "create_procurement", "approve_procurement", "view_inbound", "view_stock", "view_faults", "report_fault", "process_fault", "view_lifecycle", "manage_lifecycle", "view_disposals", "manage_disposals", "export_data"},
    "executive": {"dashboard", "view_equipment", "view_parts", "view_suppliers", "view_procurement", "view_inbound", "view_stock", "view_faults", "view_lifecycle", "view_disposals", "export_data"},
}

DEMO_ACCOUNTS = [
    ("admin", "Admin123!", "系统管理员", "admin", "信息管理部"),
    ("worker", "Worker123!", "一线工人", "worker", "生产运行部"),
    ("warehouse", "Warehouse123!", "仓库人员", "warehouse", "仓储管理部"),
    ("maintenance", "Maintenance123!", "维修工程师", "maintenance", "设备维修部"),
    ("procurement", "Procurement123!", "采购人员", "procurement", "采购供应部"),
    ("manager", "Manager123!", "中层领导", "manager", "运营管理部"),
    ("executive", "Executive123!", "高层领导", "executive", "公司领导"),
]

EN_TRANSLATIONS = {
    "备件智管平台": "Spare Parts Hub", "数据驾驶舱": "Dashboard", "设备基础信息": "Equipment",
    "备件基础信息": "Spare Parts", "供应商管理": "Suppliers", "采购比价": "Procurement & Quotes",
    "登记入库": "Inbound", "在库管理": "Inventory", "故障与领用": "Faults & Issuing",
    "故障与领用出库": "Faults & Parts Issuing", "废弃件管理": "Disposals", "寿命预警": "Lifecycle Alerts",
    "寿命预警与分级管控": "Lifecycle Alerts & Tiered Control", "用户与权限": "Users & Access",
    "工作台": "Workspace", "基础与采购": "Master Data & Procurement", "库存流转": "Inventory Flow",
    "智能管控": "Smart Control", "系统运行正常": "System Online", "退出登录": "Sign Out",
    "一物一码 · 全程可视 · 智能预警": "One item, one code · Full visibility · Smart alerts",
    "运营总览": "Operations Overview", "实时掌握库存健康度、采购进度和备件寿命风险": "Monitor inventory health, procurement and lifecycle risks in real time",
    "导出库存": "Export Inventory", "快速故障提报": "Report a Fault", "备件品规总数": "Part Specifications",
    "库存预警": "Inventory Alerts", "待审批采购": "Pending Procurement", "寿命 / 故障风险": "Lifecycle / Fault Risks",
    "备件品类分布": "Parts by Type", "寿命预警概览": "Lifecycle Alert Overview", "快捷入口": "Quick Actions",
    "库存风险清单": "Inventory Risk List", "最新操作动态": "Recent Activity", "查看全部": "View All",
    "进入库存管理": "Open Inventory", "发起采购": "Create Request", "库存盘点": "Stocktake", "故障领用": "Fault Issuing",
    "移动端故障提报": "Mobile Fault Reporting", "打开表单 →": "Open Form →", "常用业务": "Common Tasks",
    "基础信息实时统计": "Live master-data statistics", "审计留痕": "Audit Trail", "编号": "Code", "类型": "Type",
    "品目": "Category", "规格型号": "Specification", "货位": "Location", "库存": "Stock", "安全范围": "Safe Range",
    "状态": "Status", "操作": "Actions", "保存": "Save", "取消": "Cancel", "查询": "Search", "新增": "Add",
    "登录平台": "Sign In", "欢迎回来": "Welcome Back", "请使用平台账号登录管理后台": "Sign in with your platform account",
    "物流设备备件智管平台": "Logistics Equipment Spare Parts Hub", "让每一个备件": "Give Every Spare Part",
    "都有可追溯的数字生命": "a Traceable Digital Life", "贯通采购寻源、智能询比、扫码入库、库存盘点、维修领用、旧件处置和寿命预警，推动备件管理从事后补救转向事前预测与事中控制。": "Connect sourcing, quote comparison, inbound scanning, stocktaking, maintenance issuing, disposal and lifecycle alerts—from reactive fixes to predictive control.",
    "需求可预测": "Predictable Demand", "安全库存自动触发补货": "Safety stock triggers replenishment", "流转无纸化": "Paperless Flow",
    "一物一码全过程追溯": "One-code lifecycle traceability", "决策数据化": "Data-driven Decisions", "三级寿命预警与看板": "Three-level alerts and dashboards",
    "请输入用户名": "Enter username", "请输入密码": "Enter password",
    "用户名": "Username", "密码": "Password", "保持登录": "Keep me signed in", "演示账号": "Demo Accounts",
    "显示密码": "Show password", "隐藏密码": "Hide password", "一键登录": "One-click sign in",
    "用户名不存在": "Username does not exist", "密码不正确": "Incorrect password",
    "注册账户": "Create Account", "没有账户？": "No account?", "返回登录": "Back to Sign In",
    "设备故障与维修领用": "Equipment Faults & Maintenance Issuing", "本月损管比": "Monthly Loss Ratio",
    "本年度损管比": "Annual Loss Ratio", "损失金额": "Loss Amount", "同期管控基数": "Control Base",
    "演示口径：故障领用损失金额 ÷ 同期备件管控基数": "Demo metric: fault-related issuing loss divided by the parts control base",
    "故障总数": "Total Faults", "待处理": "Pending", "处理中": "In Progress", "已完成": "Completed",
    "故障编号": "Fault No.", "设备信息": "Equipment", "故障描述": "Description", "提报人": "Reporter",
    "处理结果": "Resolution", "处理工单": "Process", "故障提报": "Report Fault", "提交故障": "Submit Fault",
    "正常": "Normal", "一级预警": "Level 1 Alert", "二级预警": "Level 2 Alert", "三级预警": "Level 3 Alert",
    "紧急缺货": "Critical Shortage", "低位预警": "Low Stock", "库存偏高": "Overstock", "库存正常": "Healthy",
    "生效": "Active", "失效": "Inactive", "待定": "Pending", "已批准": "Approved", "已驳回": "Rejected",
    "运行中": "Running", "检修中": "Under Maintenance", "停用": "Out of Service", "使用中": "In Use",
    "系统管理员": "System Administrator", "一线工人": "Frontline Worker", "仓库人员": "Warehouse Staff",
    "维修工程师": "Maintenance Engineer", "采购人员": "Procurement Staff", "中层领导": "Middle Manager", "高层领导": "Executive",
    "账户注册": "Account Registration", "申请平台账户": "Request a Platform Account", "显示姓名": "Display Name",
    "所属部门": "Department", "申请角色": "Requested Role", "确认密码": "Confirm Password",
    "提交注册申请": "Submit Registration", "账户需由系统管理员审核启用后方可登录": "An administrator must approve the account before sign-in",
    "账户管理": "Account Management", "启用": "Enable", "停用账户": "Disable", "待审核": "Awaiting Approval",
    "已启用": "Enabled", "角色": "Role", "创建时间": "Created", "更新权限": "Update Access",
}

EN_TRANSLATIONS.update({
    # Page titles and shared account data
    "备品备件数字化管理平台": "Spare Parts Digital Management Platform",
    "数字化管理平台": "Digital Management Platform",
    "数据驾驶舱 - 备件智管平台": "Dashboard - Spare Parts Hub",
    "移动端故障提报": "Mobile Fault Reporting",
    "信息管理部": "Information Management Department",
    "生产运行部": "Production Operations Department",
    "仓储管理部": "Warehouse Management Department",
    "设备维修部": "Equipment Maintenance Department",
    "采购供应部": "Procurement and Supply Department",
    "运营管理部": "Operations Management Department",
    "公司领导": "Executive Office",
    "技术部": "Technology Department",
    "待分配": "Unassigned",
    "系统": "System",
    "外部用户": "External User",
    "匿名": "Anonymous",
    "当前": "Current",
    "密码须至少 8 位，并同时包含大写字母、小写字母、数字和特殊字符。": "Password must contain at least 8 characters, including uppercase and lowercase letters, a number and a special character.",

    # Dashboard metrics and dynamic descriptions
    "件实时库存": "items in real-time stock",
    "其中": "Including",
    "项紧急缺货": "critical shortages",
    "本月入库金额": "Inbound value this month",
    "个预警": "alerts",
    "个待处理故障": "pending faults",
    "传动": "Transmission",
    "气动": "Pneumatic",
    "电动": "Electric",
    "电子": "Electronic",
    "机械": "Mechanical",
    "气缸": "Cylinder",
    "电机": "Motor",
    "轴承": "Bearing",
    "剩余": "Remaining",
    "天": "days",
    "暂无寿命预警": "No lifecycle alerts",
    "所有在用备件状态良好": "All in-service parts are healthy",
    "扫码即可打开外部表单，提交后自动生成待办。": "Scan to open the external form; submission automatically creates a work item.",
    "故障提报二维码": "Fault reporting QR code",
    "备件编号": "Part Code",
    "品目 / 规格": "Category / Specification",
    "演示数据": "Demo Data",
    "平台初始化完成": "Platform initialized",
    "智能补货": "Smart Replenishment",
    "自动生成": "Automatically generated",
    "条采购需求": "procurement requests",
    "备件": "Spare Part",

    # Parts
    "备品备件目录": "Spare Parts Catalog",
    "统一维护类型、品目、规格、编码、货位与库存上下限": "Maintain type, category, specification, code, location and stock limits in one place",
    "＋ 新增备件": "+ Add Part",
    "导出目录": "Export Catalog",
    "类型 / 品目": "Type / Category",
    "分类": "Classification",
    "参考单价": "Reference Unit Price",
    "生产核心件": "Production-critical Part",
    "安全核心件": "Safety-critical Part",
    "普通非核心件": "Standard Non-critical Part",
    "新增备件基础信息": "Add Spare Part Master Data",
    "编号（留空自动生成）": "Code (leave blank to generate)",
    "实时库存": "Real-time Stock",
    "最小库存": "Minimum Stock",
    "最大库存": "Maximum Stock",
    "分级分类": "Tier Classification",
    "设计寿命（天）": "Design Life (days)",
    "保存备件": "Save Part",
    "搜索编号、品目或规格": "Search code, category or specification",
    "如：电机": "e.g. Motor",
    "如：01-01-01": "e.g. 01-01-01",
    "没有匹配的备件": "No matching parts",
    "请调整搜索条件或新增基础信息": "Change the search criteria or add master data",

    # Equipment
    "设备电子台账": "Digital Equipment Register",
    "按分拣线、设备类型和故障部位建立统一索引": "Create a unified index by sorting line, equipment type and fault location",
    "＋ 新增设备": "+ Add Equipment",
    "新增设备": "Add Equipment",
    "分拣线": "Sorting Line",
    "设备类型": "Equipment Type",
    "设备部位": "Equipment Location",
    "故障部位：": "Fault Location: ",
    "运行状态": "Operating Status",
    "保存设备": "Save Equipment",
    "如：一号标准烟分拣线": "e.g. Standard Sorting Line 1",
    "一号标准烟分拣线": "Standard Cigarette Sorting Line 1",
    "二号标准烟分拣线": "Standard Cigarette Sorting Line 2",
    "一号异型烟分拣线": "Special-format Cigarette Sorting Line 1",
    "二号异型烟分拣线": "Special-format Cigarette Sorting Line 2",
    "开箱机": "Case Opener",
    "包装机": "Packaging Machine",
    "输送设备": "Conveyor Equipment",
    "一工位": "Station 1",
    "三工位": "Station 3",
    "卧式机": "Horizontal Unit",
    "柜式机": "Cabinet Unit",
    "主传送段": "Main Conveyor Section",

    # Suppliers
    "合格供应商库": "Approved Supplier Directory",
    "维护有效期、状态、评分并关联历史供货记录": "Maintain validity, status and rating with linked supply history",
    "＋ 新增供应商": "+ Add Supplier",
    "甲供应商": "Supplier A",
    "乙供应商": "Supplier B",
    "丙供应商": "Supplier C",
    "陈经理": "Manager Chen",
    "李经理": "Manager Li",
    "王经理": "Manager Wang",
    "合作有效期": "Contract Validity",
    "综合评分": "Overall Rating",
    "历史供货记录": "Supply History",
    "由登记入库自动形成": "Automatically generated from inbound records",
    "入库单": "Inbound No.",
    "供应商": "Supplier",
    "规格": "Specification",
    "数量": "Quantity",
    "采购单价": "Purchase Unit Price",
    "金额": "Amount",
    "时间": "Time",
    "暂无供货记录": "No supply records",
    "完成登记入库后将自动沉淀历史数据": "Supply history appears automatically after inbound registration",
    "新增供应商": "Add Supplier",
    "供应商名称": "Supplier Name",
    "联系人": "Contact",
    "生效日期": "Effective Date",
    "失效日期": "Expiry Date",
    "保存供应商": "Save Supplier",
    "至": "to",

    # Procurement
    "采购寻源与智能询比": "Procurement Sourcing and Smart Quote Comparison",
    "库存预警主动发起需求，结合多家报价生成参考价格区间": "Stock alerts initiate demand and combine multiple quotes into a reference range",
    "⚡ 智能生成补货": "⚡ Generate Smart Replenishment",
    "＋ 发起采购": "+ Create Procurement",
    "预测性采购触发：": "Predictive procurement trigger: ",
    "系统按“实时库存 < 最小库存”识别风险，并建议补足到最大库存；已有待审批或已批准申请时不会重复生成。": "The system identifies risk when real-time stock is below minimum stock and recommends replenishing to maximum stock; pending or approved requests are not duplicated.",
    "采购编号": "Procurement No.",
    "采购数量": "Procurement Quantity",
    "发起时库存": "Stock at Request",
    "来源": "Source",
    "参考价格区间": "Reference Price Range",
    "建议成交价": "Suggested Price",
    "审批": "Approval",
    "暂无采购申请": "No procurement requests",
    "可由库存预警自动触发或手工发起": "Create manually or trigger automatically from a stock alert",
    "发起采购申请": "Create Procurement Request",
    "供应商 A 报价": "Supplier A Quote",
    "供应商 B 报价": "Supplier B Quote",
    "供应商 C 报价": "Supplier C Quote",
    "提交审批": "Submit for Approval",
    "批准": "Approve",
    "驳回": "Reject",
    "人工发起": "Manual Request",
    "库存预警自动触发": "Triggered by Stock Alert",
    "待审批": "Pending Approval",
    "待询价": "Awaiting Quotes",

    # Inbound
    "采购到货登记入库": "Procurement Receipt and Inbound Registration",
    "核对供应商与备件信息，入库完成后实时增加库存并沉淀供货记录": "Verify supplier and part data, update stock in real time and retain supply history",
    "＋ 登记入库": "+ Register Inbound",
    "入库单号": "Inbound No.",
    "备件信息": "Part Information",
    "合计金额": "Total Amount",
    "生产厂家": "Manufacturer",
    "经办信息": "Handled By",
    "暂无入库记录": "No inbound records",
    "到货后在此完成验收与入库": "Complete receipt inspection and inbound registration here",
    "备品备件入库表单": "Spare Parts Inbound Form",
    "当前库存": "Current Stock",
    "入库数量": "Inbound Quantity",
    "确认入库并更新库存": "Confirm Inbound and Update Stock",

    # Stock
    "库存与货位管理": "Stock and Location Management",
    "实时库存明细、库存预警、周期盘点与差异纠错": "Real-time stock, alerts, periodic stocktakes and variance correction",
    "＋ 发起盘点": "+ Start Stocktake",
    "库存总量": "Total Stock",
    "低位 / 缺货": "Low Stock / Out of Stock",
    "货位使用": "Locations Used",
    "个有效货位": "active locations",
    "实时库存明细": "Real-time Stock Details",
    "入库、领用和盘点自动更新": "Updated automatically by inbound, issuing and stocktakes",
    "库存健康度": "Stock Health",
    "最近库存流水": "Recent Stock Movements",
    "变动": "Change",
    "结存": "Balance",
    "暂无流水": "No stock movements",
    "最近盘点": "Recent Stocktakes",
    "盘点单": "Stocktake No.",
    "账面 / 实盘": "Book / Actual",
    "结果": "Result",
    "暂无盘点记录": "No stocktake records",
    "盘点方式": "Stocktake Type",
    "日常抽盘": "Routine Sample Count",
    "定期整盘": "Scheduled Full Count",
    "账面库存": "Book Stock",
    "实盘数量": "Actual Quantity",
    "差异原因（账实不符时必填）": "Variance Reason (required when different)",
    "提交盘点结果": "Submit Stocktake Result",
    "如：历史登记差错、损耗等": "e.g. historical entry error or loss",
    "采购入库": "Procurement Inbound",
    "盘点纠错": "Stocktake Correction",
    "账实相符": "Book and Actual Match",
    "账实不符-已纠错": "Variance Corrected",

    # Faults
    "故障工单强关联领用记录，自动校验库存并建立备件寿命档案": "Fault orders link to issuing records, validate stock and create part lifecycle records",
    "移动端表单": "Mobile Form",
    "暂无故障工单": "No fault orders",
    "可从后台或移动端扫码提报": "Report from the console or scan on mobile",
    "设备故障移动提报": "Mobile Equipment Fault Reporting",
    "扫码提交 · 自动生成待办": "Scan to Submit · Work Order Created Automatically",
    "故障发生后请准确选择设备，并简要描述现场现象。": "Select the correct equipment and briefly describe what happened on site.",
    "手机或内线": "Mobile or extension number",
    "例如：开箱机三工位运行时出现异响并停机": "Example: The case opener at Station 3 made an unusual noise and stopped.",
    "设备故障提报": "Equipment Fault Report",
    "故障设备": "Faulty Equipment",
    "联系方式": "Contact Details",
    "请描述故障现象、异常位置等": "Describe the fault symptoms and abnormal location",
    "处理故障": "Process Fault",
    "处理办法": "Resolution Method",
    "是否需要更换零件": "Replacement Required",
    "否，现场处理完成": "No, resolved on site",
    "是，发起备件领用": "Yes, issue a spare part",
    "领用备件": "Part to Issue",
    "领用数量": "Issue Quantity",
    "旧件是否有价值": "Old Part Has Value",
    "无价值": "No Value",
    "有价值": "Has Value",
    "完成处理并闭环": "Complete Resolution and Close",
    "领用出库": "Maintenance Issue",

    # Lifecycle
    "在用备件寿命档案": "In-service Part Lifecycle Records",
    "一级：剩余 20% 纳入月维保；二级：剩余 10% 纳入周维保；三级：到期立即更换": "Level 1: include in monthly maintenance at 20% remaining; Level 2: weekly maintenance at 10%; Level 3: replace immediately at expiry",
    "分级更换规则：": "Tiered replacement rules: ",
    "导出预警报表": "Export Alert Report",
    "安全核心件到期强制更换；生产核心件和普通非核心件经现场判断后可申请延期，系统自动重算预警日期。": "Safety-critical parts must be replaced at expiry; production-critical and standard non-critical parts may request an extension after inspection, with alert dates recalculated automatically.",
    "状态正常": "Normal Status",
    "寿命编号": "Lifecycle No.",
    "安装设备": "Installed Equipment",
    "安装 / 到期": "Installed / Due",
    "剩余寿命": "Remaining Life",
    "预警": "Alert",
    "到期": "Due",
    "已延期": "Extended",
    "申请延期": "Request Extension",
    "确认更换": "Confirm Replacement",
    "只读": "Read Only",
    "暂无寿命档案": "No lifecycle records",
    "故障领用完成后会自动建立": "Created automatically after fault-related issuing",
    "延期使用申请": "Service Extension Request",
    "延期天数": "Extension Days",
    "申请人": "Applicant",
    "现场判断意见": "Inspection Assessment",
    "提交延期": "Submit Extension",
    "请说明可继续使用的检查依据": "Provide inspection evidence supporting continued use",
    "确认将该备件标记为已更换？": "Mark this part as replaced?",
    "已更换": "Replaced",
    "已关闭": "Closed",

    # Disposals
    "旧件鉴定与逆向物流": "Old Part Assessment and Reverse Logistics",
    "领用出库自动带入旧件，按可复用性和残值形成处置闭环": "Issued parts automatically create old-part records for reuse and residual-value disposition",
    "待鉴定": "Awaiting Assessment",
    "待二次使用": "Awaiting Reuse",
    "待残值处置": "Awaiting Residual-value Disposal",
    "已报废": "Scrapped",
    "来源领用单": "Source Issue No.",
    "旧件信息": "Old Part Information",
    "是否有价值": "Has Value",
    "是否可复用": "Reusable",
    "处置状态": "Disposal Status",
    "意见 / 收益": "Assessment / Proceeds",
    "鉴定": "Assessment",
    "是": "Yes",
    "否": "No",
    "处置收益": "Disposal Proceeds",
    "处置鉴定": "Assess",
    "暂无旧件记录": "No old-part records",
    "故障领用后自动进入鉴定流程": "Enters assessment automatically after fault-related issuing",
    "旧件鉴定": "Old Part Assessment",
    "旧件价值": "Old Part Value",
    "是否还可使用": "Still Reusable",
    "否，进入报废/残值处置": "No, proceed to scrap or residual-value disposal",
    "是，待二次使用": "Yes, awaiting reuse",
    "拟处理意见": "Proposed Disposition",
    "如：返厂维修、回收入库、残值变卖、无价值报废": "e.g. return for repair, recover to stock, sell residual value or scrap",
    "保存鉴定结果": "Save Assessment",

    # Users and permissions
    "审核注册申请、分配角色并管理账户启停状态": "Review registrations, assign roles and manage account status",
    "个账户": "accounts",
    "开启时，每次启动都会恢复七个演示账户的角色、启用状态和预设密码，避免旧数据库密码导致无法登录。": "When enabled, every startup restores the seven demo accounts, roles, status and passwords.",
    "角色权限矩阵": "Role Permission Matrix",
    "最小权限原则": "Principle of Least Privilege",
    "全部系统权限": "All System Permissions",
    "故障提报": "Fault Reporting",
    "查看设备/备件": "View Equipment / Parts",
    "备件/入库/库存/旧件": "Parts / Inbound / Stock / Old Parts",
    "故障处理/寿命/旧件": "Faults / Lifecycle / Old Parts",
    "供应商/采购/入库查看": "Suppliers / Procurement / Inbound View",
    "业务管理/采购审批": "Business Management / Procurement Approval",
    "全局只读/报表": "Global Read-only / Reports",

    # Registration, feedback and errors
    "请先登录后继续操作": "Please sign in to continue",
    "用户名或密码错误": "Incorrect username or password",
    "账户正在等待管理员审核": "Account is awaiting administrator approval",
    "用户名须以字母开头，仅含字母、数字或下划线，长度 3-32 位": "Username must start with a letter and contain 3-32 letters, numbers or underscores",
    "用户名已被使用": "Username is already in use",
    "申请角色无效": "Invalid requested role",
    "两次输入的密码不一致": "Passwords do not match",
    "密码至少 8 位，并包含大小写字母、数字和特殊字符": "Password must be at least 8 characters with uppercase, lowercase, number and special character",
    "注册申请已提交，请等待系统管理员审核": "Registration submitted; please wait for administrator approval",
    "当前账号没有此项审批权限": "This account does not have permission for this action",
    "您访问的内容不存在": "The requested content does not exist",
    "已安全退出": "Signed out safely",
    "不能停用演示管理员账户": "The demo administrator account cannot be disabled",
    "账户角色与状态已更新": "Account role and status updated",
    "备件编号已存在": "The part code already exists",
    "备件基础信息已新增": "Spare part master data added",
    "供应商已加入合格供应商库": "Supplier added to the approved supplier directory",
    "设备台账已更新": "Equipment register updated",
    "采购申请已发起，进入审批流程": "Procurement request submitted for approval",
    "已根据安全库存生成": "Generated from safety-stock rules:",
    "入库数量必须大于 0": "Inbound quantity must be greater than zero",
    "入库成功，库存已实时更新": "Inbound completed and stock updated in real time",
    "盘点已完成：": "Stocktake completed: ",
    "故障": "Fault",
    "已提报": "reported",
    "领用数量无效或大于实时库存": "Issue quantity is invalid or exceeds real-time stock",
    "故障处理完成，库存与寿命档案已联动更新": "Fault processing completed; stock and lifecycle records were updated",
    "安全核心件到期必须强制更换，不允许延期": "Expired safety-critical parts must be replaced and cannot be extended",
    "延期天数须在 1-365 天之间": "Extension must be between 1 and 365 days",
    "延期申请已记录，预警日期已重新计算": "Extension recorded and the alert date recalculated",
    "备件已标记为更换完成": "The part has been marked as replaced",
    "旧件鉴定结果已保存": "Old-part assessment saved",
    "故障提报成功": "Fault Report Submitted",
    "工单编号：": "Work Order No.: ",
    "技术人员将尽快处理，请妥善保存工单编号。": "A technician will respond shortly. Please keep the work order number.",
    "继续提报": "Submit Another Report",
    "访问提示": "Access Notice",
    "您可以返回数据驾驶舱继续操作。": "Return to the dashboard to continue.",
    "返回首页": "Back to Dashboard",
    "登录 - 备件智管平台": "Sign In - Spare Parts Hub",
    "登录": "Sign In",
})


TRANSLATION_ITEMS = tuple(sorted(EN_TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True))
TRANSLATABLE_ATTRIBUTE_RE = re.compile(
    r"(?P<prefix>\s(?:placeholder|aria-label|title|alt|data-confirm|data-show-label|data-hide-label)=)"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
HTML_TOKEN_RE = re.compile(
    r"(<script\b.*?</script\s*>|<style\b.*?</style\s*>|<!--.*?-->|<[^>]+>|[^<]+)",
    re.IGNORECASE | re.DOTALL,
)


def translate_english_text(value):
    """Translate known Chinese UI fragments while preserving surrounding content."""
    if value is None:
        return value
    source = str(value)
    stripped = source.strip()
    if stripped in EN_TRANSLATIONS:
        return source.replace(stripped, EN_TRANSLATIONS[stripped])
    translated = source
    for chinese, english in TRANSLATION_ITEMS:
        if chinese in translated:
            translated = translated.replace(chinese, english)
    return translated


def translate_english_html(document):
    """Translate user-facing HTML without changing form values, URLs or scripts."""
    def translate_attribute(match):
        value = translate_english_text(match.group("value"))
        return f'{match.group("prefix")}{match.group("quote")}{value}{match.group("quote")}'

    translated_tokens = []
    for match in HTML_TOKEN_RE.finditer(document):
        token = match.group(0)
        lowered = token.lstrip().lower()
        if lowered.startswith(("<script", "<style", "<!--")):
            translated_tokens.append(token)
        elif lowered.startswith("<"):
            translated_tokens.append(TRANSLATABLE_ATTRIBUTE_RE.sub(translate_attribute, token))
        else:
            translated_tokens.append(translate_english_text(token))
    return "".join(translated_tokens)


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def next_number(prefix: str, model) -> str:
    today = date.today().strftime("%Y%m%d")
    count = model.query.filter(model.number.like(f"{prefix}-{today}-%")).count() + 1
    return f"{prefix}-{today}-{count:04d}"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(80), default="技术部")
    role = db.Column(db.String(30), default="worker")
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=now)
    preferred_language = db.Column(db.String(5), default="zh")

    @property
    def is_active(self):
        return self.active


class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    line_name = db.Column(db.String(80), nullable=False)
    device_type = db.Column(db.String(80), nullable=False)
    location = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(30), default="运行中")

    @property
    def full_name(self):
        return f"{self.line_name} / {self.device_type} / {self.location}"


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    contact = db.Column(db.String(80), default="")
    effective_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(30), default="生效")
    score = db.Column(db.Integer, default=90)


class Part(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)
    part_type = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    specification = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(50), nullable=False)
    stock = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer, default=0)
    max_stock = db.Column(db.Integer, default=0)
    classification = db.Column(db.String(30), default="普通非核心件")
    service_life_days = db.Column(db.Integer, default=365)
    unit_price = db.Column(db.Float, default=0)

    @property
    def stock_status(self):
        if self.stock <= 0:
            return "紧急缺货"
        if self.stock < self.min_stock:
            return "低位预警"
        if self.max_stock and self.stock > self.max_stock:
            return "库存偏高"
        return "库存正常"


class Procurement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    real_stock = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(30), default="人工发起")
    handler = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(80), nullable=False)
    quote_a = db.Column(db.Float, default=0)
    quote_b = db.Column(db.Float, default=0)
    quote_c = db.Column(db.Float, default=0)
    selected_price = db.Column(db.Float, default=0)
    status = db.Column(db.String(30), default="待审批")
    created_at = db.Column(db.DateTime, default=now)
    part = db.relationship("Part")

    @property
    def reference_range(self):
        quotes = [q for q in (self.quote_a, self.quote_b, self.quote_c) if q and q > 0]
        if not quotes:
            return "待询价"
        return f"¥{min(quotes):,.0f} - ¥{max(quotes):,.0f}"


class Inbound(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    manufacturer = db.Column(db.String(100), nullable=False)
    operator = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=now)
    part = db.relationship("Part")
    supplier = db.relationship("Supplier")

    @property
    def total(self):
        return self.quantity * self.unit_price


class InventoryTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)
    movement = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    balance = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(80), nullable=False)
    operator = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=now)
    part = db.relationship("Part")


class Stocktake(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)
    stock_before = db.Column(db.Integer, nullable=False)
    actual_stock = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), default="")
    stocktake_type = db.Column(db.String(30), default="日常抽盘")
    operator = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(80), nullable=False)
    result = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, default=now)
    part = db.relationship("Part")


class FaultReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipment.id"), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    reporter = db.Column(db.String(50), nullable=False)
    contact = db.Column(db.String(80), default="")
    status = db.Column(db.String(30), default="待处理")
    handler = db.Column(db.String(50), default="")
    handling = db.Column(db.String(500), default="")
    need_replacement = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now)
    processed_at = db.Column(db.DateTime)
    equipment = db.relationship("Equipment")


class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), unique=True, nullable=False)
    fault_id = db.Column(db.Integer, db.ForeignKey("fault_report.id"), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    requester = db.Column(db.String(50), nullable=False)
    old_part_value = db.Column(db.String(20), default="无价值")
    created_at = db.Column(db.DateTime, default=now)
    fault = db.relationship("FaultReport")
    part = db.relationship("Part")


class Lifecycle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    serial_number = db.Column(db.String(50), unique=True, nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipment.id"), nullable=False)
    withdrawal_id = db.Column(db.Integer, db.ForeignKey("withdrawal.id"))
    installed_at = db.Column(db.DateTime, nullable=False)
    expected_life_days = db.Column(db.Integer, nullable=False)
    classification = db.Column(db.String(30), nullable=False)
    extension_days = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default="使用中")
    part = db.relationship("Part")
    equipment = db.relationship("Equipment")
    withdrawal = db.relationship("Withdrawal")

    @property
    def total_life_days(self):
        return self.expected_life_days + self.extension_days

    @property
    def used_days(self):
        return max(0, (now() - self.installed_at).days)

    @property
    def remaining_days(self):
        return self.total_life_days - self.used_days

    @property
    def remaining_percent(self):
        if self.total_life_days <= 0:
            return 0
        return round(self.remaining_days / self.total_life_days * 100)

    @property
    def warning_level(self):
        if self.status != "使用中":
            return "已关闭"
        if self.remaining_days <= 0:
            return "三级预警"
        if self.remaining_percent <= 10:
            return "二级预警"
        if self.remaining_percent <= 20:
            return "一级预警"
        return "正常"

    @property
    def due_date(self):
        return (self.installed_at + timedelta(days=self.total_life_days)).date()


class Disposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    withdrawal_id = db.Column(db.Integer, db.ForeignKey("withdrawal.id"), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey("part.id"), nullable=False)
    valuable = db.Column(db.Boolean, default=False)
    reusable = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(30), default="待鉴定")
    opinion = db.Column(db.String(255), default="")
    proceeds = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=now)
    withdrawal = db.relationship("Withdrawal")
    part = db.relationship("Part")


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    detail = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def audit(action: str, detail: str):
    name = current_user.display_name if current_user.is_authenticated else "外部用户"
    db.session.add(AuditLog(user_name=name, action=action, detail=detail))


def has_permission(permission: str, user=None) -> bool:
    user = user or current_user
    if not getattr(user, "is_authenticated", False):
        return False
    permissions = ROLE_PERMISSIONS.get(user.role, set())
    return "*" in permissions or permission in permissions


def permission_required(permission):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if not has_permission(permission):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_permission(permission):
    if not has_permission(permission):
        abort(403)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def csrf_protect():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    if request.method == "POST":
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not secrets.compare_digest(token, session["csrf_token"]):
            abort(400, "CSRF token invalid")


@app.after_request
def translate_english_response(response):
    """Render English UI on the server so browser cache or JavaScript cannot cause fallback text."""
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        if session.get("lang", "zh") == "en" and not response.direct_passthrough:
            response.set_data(translate_english_html(response.get_data(as_text=True)))
    return response


@app.context_processor
def inject_globals():
    current_lang = session.get("lang", "zh")

    def translate(value):
        if value is None or current_lang == "zh":
            return value
        return translate_english_text(value)

    def role_name(role):
        names = ROLE_NAMES.get(role, (role, role))
        return names[1] if current_lang == "en" else names[0]

    return {
        "csrf_token": session.get("csrf_token", ""),
        "today": date.today(),
        "current_lang": current_lang,
        "translations": EN_TRANSLATIONS if current_lang == "en" else {},
        "t": translate,
        "role_name": role_name,
        "can": has_permission,
        "demo_mode": DEMO_MODE,
        "app_version": APP_VERSION,
    }


@app.template_filter("datetime")
def format_datetime(value):
    return value.strftime("%Y-%m-%d %H:%M") if value else "-"


@app.template_filter("money")
def format_money(value):
    return f"¥{float(value or 0):,.2f}"


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = unicodedata.normalize("NFKC", request.form.get("username", "")).strip()
        user = User.query.filter_by(username=username).first()
        password = request.form.get("password", "")
        demo_usernames = {account[0] for account in DEMO_ACCOUNTS}
        if DEMO_MODE and user and user.username in demo_usernames:
            password = unicodedata.normalize("NFKC", password).strip()
        password_ok = bool(user and check_password_hash(user.password_hash, password))
        if user and password_ok and user.active:
            login_user(user, remember=bool(request.form.get("remember")))
            selected_language = session.get("lang") or user.preferred_language or "zh"
            session["lang"] = selected_language
            if user.preferred_language != selected_language:
                user.preferred_language = selected_language
                db.session.commit()
            return redirect(request.args.get("next") or url_for("dashboard"))
        if not user:
            flash("用户名不存在" if DEMO_MODE else "用户名或密码错误", "danger")
        elif not password_ok:
            flash("密码不正确" if DEMO_MODE else "用户名或密码错误", "danger")
        elif not user.active:
            flash("账户正在等待管理员审核", "warning")
            return render_template("login.html", demo_accounts=DEMO_ACCOUNTS if DEMO_MODE else [])
    return render_template("login.html", demo_accounts=DEMO_ACCOUNTS if DEMO_MODE else [])


@app.route("/language/<lang>")
def set_language(lang):
    if lang not in {"zh", "en"}:
        abort(404)
    session["lang"] = lang
    if current_user.is_authenticated:
        current_user.preferred_language = lang
        db.session.commit()
    target = request.referrer
    if not target or not target.startswith(request.host_url):
        target = url_for("dashboard") if current_user.is_authenticated else url_for("login")
    return redirect(target)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    public_roles = {key: value for key, value in ROLE_NAMES.items() if key != "admin"}
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        role = request.form.get("role", "worker")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,31}", username):
            flash("用户名须以字母开头，仅含字母、数字或下划线，长度 3-32 位", "danger")
        elif User.query.filter_by(username=username).first():
            flash("用户名已被使用", "danger")
        elif role not in public_roles:
            flash("申请角色无效", "danger")
        elif password != confirm:
            flash("两次输入的密码不一致", "danger")
        elif len(password) < 8 or not all((re.search(r"[A-Z]", password), re.search(r"[a-z]", password), re.search(r"\d", password), re.search(r"[^A-Za-z0-9]", password))):
            flash("密码至少 8 位，并包含大小写字母、数字和特殊字符", "danger")
        else:
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                display_name=request.form.get("display_name", "").strip() or username,
                department=request.form.get("department", "").strip() or "待分配",
                role=role,
                active=False,
                preferred_language=session.get("lang", "zh"),
            )
            db.session.add(user)
            audit("账户注册", f"{username} 申请 {ROLE_NAMES[role][0]}")
            db.session.commit()
            flash("注册申请已提交，请等待系统管理员审核", "success")
            return redirect(url_for("login"))
    return render_template("register.html", public_roles=public_roles)


@app.route("/users")
@admin_required
def users():
    return render_template("users.html", users=User.query.order_by(User.created_at.desc()).all(), roles=ROLE_NAMES)


@app.route("/users/<int:user_id>/update", methods=["POST"])
@admin_required
def update_user(user_id):
    user = db.get_or_404(User, user_id)
    role = request.form.get("role", user.role)
    if role not in ROLE_NAMES:
        abort(400)
    if user.username == "admin" and request.form.get("active") != "yes":
        flash("不能停用演示管理员账户", "danger")
        return redirect(url_for("users"))
    user.role = role
    user.active = request.form.get("active") == "yes"
    audit("权限更新", f"{user.username} -> {ROLE_NAMES[role][0]} / {'启用' if user.active else '停用'}")
    db.session.commit()
    flash("账户角色与状态已更新", "success")
    return redirect(url_for("users"))


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("已安全退出", "success")
    return redirect(url_for("login"))


@app.route("/")
@login_required
@permission_required("dashboard")
def dashboard():
    parts = Part.query.order_by(Part.stock.asc()).all()
    lifecycles = Lifecycle.query.filter_by(status="使用中").all()
    warnings = [item for item in lifecycles if item.warning_level != "正常"]
    recent = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(8).all()
    month_start = now().replace(day=1, hour=0, minute=0, second=0)
    inbound_total = (
        db.session.query(func.coalesce(func.sum(Inbound.quantity * Inbound.unit_price), 0))
        .filter(Inbound.created_at >= month_start)
        .scalar()
    )
    return render_template(
        "dashboard.html",
        parts=parts,
        low_parts=[p for p in parts if p.stock < p.min_stock],
        warnings=sorted(warnings, key=lambda x: x.remaining_days),
        pending_procurement=Procurement.query.filter_by(status="待审批").count(),
        open_faults=FaultReport.query.filter(FaultReport.status != "已完成").count(),
        inbound_total=inbound_total,
        recent=recent,
        type_counts=dict(
            db.session.query(Part.part_type, func.count(Part.id)).group_by(Part.part_type).all()
        ),
    )


@app.route("/parts", methods=["GET", "POST"])
@login_required
@permission_required("view_parts")
def parts():
    if request.method == "POST":
        require_permission("manage_parts")
        part_type = request.form["part_type"].strip()
        category = request.form["category"].strip()
        specification = request.form["specification"].strip()
        base_code = f"{part_type[:2].upper()}-{category[:2].upper()}-{specification.upper().replace(' ', '')}"
        code = request.form.get("code", "").strip() or base_code
        if Part.query.filter_by(code=code).first():
            flash("备件编号已存在", "danger")
        else:
            part = Part(
                code=code,
                part_type=part_type,
                category=category,
                specification=specification,
                location=request.form["location"].strip(),
                stock=int(request.form.get("stock") or 0),
                min_stock=int(request.form.get("min_stock") or 0),
                max_stock=int(request.form.get("max_stock") or 0),
                classification=request.form["classification"],
                service_life_days=int(request.form.get("service_life_days") or 365),
                unit_price=float(request.form.get("unit_price") or 0),
            )
            db.session.add(part)
            audit("新增备件", f"{code} {specification}")
            db.session.commit()
            flash("备件基础信息已新增", "success")
            return redirect(url_for("parts"))
    keyword = request.args.get("q", "").strip()
    query = Part.query
    if keyword:
        query = query.filter(
            or_(Part.code.contains(keyword), Part.category.contains(keyword), Part.specification.contains(keyword))
        )
    return render_template("parts.html", parts=query.order_by(Part.code).all(), keyword=keyword)


@app.route("/suppliers", methods=["GET", "POST"])
@login_required
@permission_required("view_suppliers")
def suppliers():
    if request.method == "POST":
        require_permission("manage_suppliers")
        supplier = Supplier(
            name=request.form["name"].strip(),
            contact=request.form.get("contact", "").strip(),
            effective_date=date.fromisoformat(request.form["effective_date"]),
            expiry_date=date.fromisoformat(request.form["expiry_date"]),
            status=request.form["status"],
            score=int(request.form.get("score") or 90),
        )
        db.session.add(supplier)
        audit("新增供应商", supplier.name)
        db.session.commit()
        flash("供应商已加入合格供应商库", "success")
        return redirect(url_for("suppliers"))
    history = Inbound.query.order_by(Inbound.created_at.desc()).limit(20).all()
    return render_template("suppliers.html", suppliers=Supplier.query.all(), history=history)


@app.route("/equipment", methods=["GET", "POST"])
@login_required
@permission_required("view_equipment")
def equipment():
    if request.method == "POST":
        require_permission("manage_equipment")
        item = Equipment(
            line_name=request.form["line_name"].strip(),
            device_type=request.form["device_type"].strip(),
            location=request.form["location"].strip(),
            status=request.form["status"],
        )
        db.session.add(item)
        audit("新增设备", item.full_name)
        db.session.commit()
        flash("设备台账已更新", "success")
        return redirect(url_for("equipment"))
    return render_template("equipment.html", equipment=Equipment.query.order_by(Equipment.line_name).all())


@app.route("/procurement", methods=["GET", "POST"])
@login_required
@permission_required("view_procurement")
def procurement():
    if request.method == "POST":
        require_permission("create_procurement")
        part = db.get_or_404(Part, int(request.form["part_id"]))
        item = Procurement(
            number=next_number("CG", Procurement),
            part=part,
            quantity=int(request.form["quantity"]),
            real_stock=part.stock,
            source="人工发起",
            handler=current_user.display_name,
            department=current_user.department,
            quote_a=float(request.form.get("quote_a") or 0),
            quote_b=float(request.form.get("quote_b") or 0),
            quote_c=float(request.form.get("quote_c") or 0),
        )
        quotes = [q for q in (item.quote_a, item.quote_b, item.quote_c) if q > 0]
        item.selected_price = min(quotes) if quotes else 0
        db.session.add(item)
        audit("发起采购", f"{item.number} {part.code} × {item.quantity}")
        db.session.commit()
        flash("采购申请已发起，进入审批流程", "success")
        return redirect(url_for("procurement"))
    return render_template(
        "procurement.html",
        parts=Part.query.order_by(Part.code).all(),
        items=Procurement.query.order_by(Procurement.created_at.desc()).all(),
    )


@app.route("/procurement/generate", methods=["POST"])
@login_required
@permission_required("create_procurement")
def generate_procurement():
    created = 0
    for part in Part.query.all():
        exists = Procurement.query.filter(
            Procurement.part_id == part.id,
            Procurement.status.in_(["待审批", "已批准"]),
        ).first()
        if part.stock < part.min_stock and not exists:
            quantity = max(part.max_stock - part.stock, part.min_stock - part.stock, 1)
            item = Procurement(
                number=next_number("CG", Procurement),
                part=part,
                quantity=quantity,
                real_stock=part.stock,
                source="库存预警自动触发",
                handler=current_user.display_name,
                department=current_user.department,
                selected_price=part.unit_price,
            )
            db.session.add(item)
            db.session.flush()
            created += 1
    audit("智能补货", f"自动生成 {created} 条采购需求")
    db.session.commit()
    flash(f"已根据安全库存生成 {created} 条采购需求", "success")
    return redirect(url_for("procurement"))


@app.route("/procurement/<int:item_id>/<action>", methods=["POST"])
@permission_required("approve_procurement")
def procurement_action(item_id, action):
    item = db.get_or_404(Procurement, item_id)
    if action not in {"approve", "reject"}:
        abort(404)
    item.status = "已批准" if action == "approve" else "已驳回"
    audit("采购审批", f"{item.number} {item.status}")
    db.session.commit()
    flash(f"采购申请已{item.status}", "success")
    return redirect(url_for("procurement"))


@app.route("/inbound", methods=["GET", "POST"])
@login_required
@permission_required("view_inbound")
def inbound():
    if request.method == "POST":
        require_permission("manage_inbound")
        part = db.get_or_404(Part, int(request.form["part_id"]))
        supplier = db.get_or_404(Supplier, int(request.form["supplier_id"]))
        quantity = int(request.form["quantity"])
        if quantity <= 0:
            flash("入库数量必须大于 0", "danger")
            return redirect(url_for("inbound"))
        item = Inbound(
            number=next_number("RKD", Inbound),
            part=part,
            supplier=supplier,
            quantity=quantity,
            unit_price=float(request.form["unit_price"]),
            manufacturer=request.form["manufacturer"].strip(),
            operator=current_user.display_name,
            department=current_user.department,
        )
        part.stock += quantity
        part.unit_price = item.unit_price
        db.session.add(item)
        db.session.flush()
        db.session.add(
            InventoryTransaction(
                part=part,
                movement="采购入库",
                quantity=quantity,
                balance=part.stock,
                reference=item.number,
                operator=current_user.display_name,
            )
        )
        audit("登记入库", f"{item.number} {part.code} +{quantity}")
        db.session.commit()
        flash(f"{item.number} 入库成功，库存已实时更新", "success")
        return redirect(url_for("inbound"))
    return render_template(
        "inbound.html",
        parts=Part.query.order_by(Part.code).all(),
        suppliers=Supplier.query.filter_by(status="生效").all(),
        records=Inbound.query.order_by(Inbound.created_at.desc()).all(),
    )


@app.route("/stock", methods=["GET", "POST"])
@login_required
@permission_required("view_stock")
def stock():
    if request.method == "POST":
        require_permission("manage_stock")
        part = db.get_or_404(Part, int(request.form["part_id"]))
        actual = int(request.form["actual_stock"])
        before = part.stock
        result = "账实相符" if actual == before else "账实不符-已纠错"
        item = Stocktake(
            number=next_number("PD", Stocktake),
            part=part,
            stock_before=before,
            actual_stock=actual,
            reason=request.form.get("reason", "").strip(),
            stocktake_type=request.form["stocktake_type"],
            operator=current_user.display_name,
            department=current_user.department,
            result=result,
        )
        db.session.add(item)
        if actual != before:
            part.stock = actual
            db.session.add(
                InventoryTransaction(
                    part=part,
                    movement="盘点纠错",
                    quantity=actual - before,
                    balance=actual,
                    reference=item.number,
                    operator=current_user.display_name,
                )
            )
        audit("库存盘点", f"{item.number} {part.code} {result}")
        db.session.commit()
        flash(f"盘点已完成：{result}", "success" if actual == before else "warning")
        return redirect(url_for("stock"))
    return render_template(
        "stock.html",
        parts=Part.query.order_by(Part.stock.asc()).all(),
        transactions=InventoryTransaction.query.order_by(InventoryTransaction.created_at.desc()).limit(50).all(),
        stocktakes=Stocktake.query.order_by(Stocktake.created_at.desc()).limit(20).all(),
    )


def create_fault_from_form(public=False):
    equipment_item = db.get_or_404(Equipment, int(request.form["equipment_id"]))
    item = FaultReport(
        number=next_number("GZ", FaultReport),
        equipment=equipment_item,
        description=request.form["description"].strip(),
        reporter=request.form.get("reporter", "").strip() or (current_user.display_name if current_user.is_authenticated else "匿名"),
        contact=request.form.get("contact", "").strip(),
    )
    db.session.add(item)
    audit("故障提报", f"{item.number} {equipment_item.full_name}")
    db.session.commit()
    return item


@app.route("/faults", methods=["GET", "POST"])
@login_required
@permission_required("view_faults")
def faults():
    if request.method == "POST":
        require_permission("report_fault")
        item = create_fault_from_form()
        flash(f"故障 {item.number} 已提报", "success")
        return redirect(url_for("faults"))
    return render_template(
        "faults.html",
        equipment=Equipment.query.all(),
        parts=Part.query.order_by(Part.code).all(),
        faults=FaultReport.query.order_by(FaultReport.created_at.desc()).all(),
        damage_ratios={
            "month": {"ratio": 2.8, "loss": 12800, "base": 457000},
            "year": {"ratio": 3.6, "loss": 146000, "base": 4050000},
        },
    )


@app.route("/fault-report", methods=["GET", "POST"])
def public_fault():
    submitted = None
    if request.method == "POST":
        submitted = create_fault_from_form(public=True)
    return render_template(
        "public_fault.html", equipment=Equipment.query.all(), submitted=submitted
    )


@app.route("/fault-report/qr.png")
def fault_qr():
    base_url = PUBLIC_BASE_URL or request.url_root.rstrip("/")
    target = base_url + url_for("public_fault")
    image = qrcode.make(target)
    stream = io.BytesIO()
    image.save(stream, "PNG")
    stream.seek(0)
    return send_file(stream, mimetype="image/png", download_name="fault-report-qr.png")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": APP_VERSION}


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


@app.route("/faults/<int:fault_id>/process", methods=["POST"])
@login_required
@permission_required("process_fault")
def process_fault(fault_id):
    fault = db.get_or_404(FaultReport, fault_id)
    need_replacement = request.form.get("need_replacement") == "yes"
    fault.handler = current_user.display_name
    fault.handling = request.form["handling"].strip()
    fault.need_replacement = need_replacement
    fault.processed_at = now()
    if not need_replacement:
        fault.status = "已完成"
    else:
        part = db.get_or_404(Part, int(request.form["part_id"]))
        quantity = int(request.form["quantity"])
        if quantity <= 0 or quantity > part.stock:
            flash("领用数量无效或大于实时库存", "danger")
            return redirect(url_for("faults"))
        withdrawal = Withdrawal(
            number=next_number("LY", Withdrawal),
            fault=fault,
            part=part,
            quantity=quantity,
            requester=current_user.display_name,
            old_part_value=request.form.get("old_part_value", "无价值"),
        )
        part.stock -= quantity
        fault.status = "已完成"
        db.session.add(withdrawal)
        db.session.flush()
        db.session.add(
            InventoryTransaction(
                part=part,
                movement="领用出库",
                quantity=-quantity,
                balance=part.stock,
                reference=withdrawal.number,
                operator=current_user.display_name,
            )
        )
        for index in range(quantity):
            serial = f"SM-{date.today().strftime('%Y%m%d')}-{withdrawal.id:04d}-{index + 1:02d}"
            db.session.add(
                Lifecycle(
                    serial_number=serial,
                    part=part,
                    equipment=fault.equipment,
                    withdrawal=withdrawal,
                    installed_at=now(),
                    expected_life_days=part.service_life_days,
                    classification=part.classification,
                )
            )
        db.session.add(
            Disposal(
                withdrawal=withdrawal,
                part=part,
                valuable=withdrawal.old_part_value == "有价值",
            )
        )
    audit("故障处理", f"{fault.number} {fault.status}")
    db.session.commit()
    flash("故障处理完成，库存与寿命档案已联动更新", "success")
    return redirect(url_for("faults"))


@app.route("/lifecycle")
@login_required
@permission_required("view_lifecycle")
def lifecycle():
    items = Lifecycle.query.order_by(Lifecycle.installed_at.desc()).all()
    return render_template("lifecycle.html", items=items)


@app.route("/lifecycle/<int:item_id>/<action>", methods=["POST"])
@login_required
@permission_required("manage_lifecycle")
def lifecycle_action(item_id, action):
    item = db.get_or_404(Lifecycle, item_id)
    if action == "extend":
        if item.classification == "安全核心件":
            flash("安全核心件到期必须强制更换，不允许延期", "danger")
            return redirect(url_for("lifecycle"))
        days = int(request.form.get("days") or 0)
        if days <= 0 or days > 365:
            flash("延期天数须在 1-365 天之间", "danger")
            return redirect(url_for("lifecycle"))
        item.extension_days += days
        audit("寿命延期", f"{item.serial_number} 延期 {days} 天")
        flash("延期申请已记录，预警日期已重新计算", "success")
    elif action == "replace":
        item.status = "已更换"
        audit("到期更换", item.serial_number)
        flash("备件已标记为更换完成", "success")
    else:
        abort(404)
    db.session.commit()
    return redirect(url_for("lifecycle"))


@app.route("/disposals")
@login_required
@permission_required("view_disposals")
def disposals():
    return render_template(
        "disposals.html", items=Disposal.query.order_by(Disposal.created_at.desc()).all()
    )


@app.route("/disposals/<int:item_id>/decide", methods=["POST"])
@login_required
@permission_required("manage_disposals")
def disposal_decide(item_id):
    item = db.get_or_404(Disposal, item_id)
    item.reusable = request.form.get("reusable") == "yes"
    item.opinion = request.form.get("opinion", "").strip()
    item.proceeds = float(request.form.get("proceeds") or 0)
    if item.reusable:
        item.status = "待二次使用"
    elif item.valuable:
        item.status = "待残值处置"
    else:
        item.status = "已报废"
    audit("旧件鉴定", f"{item.withdrawal.number} {item.status}")
    db.session.commit()
    flash("旧件鉴定结果已保存", "success")
    return redirect(url_for("disposals"))


@app.route("/export/<kind>.csv")
@login_required
@permission_required("export_data")
def export_csv(kind):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    if kind == "stock":
        writer.writerow(["编号", "类型", "品目", "规格型号", "货位", "实时库存", "最小库存", "最大库存", "状态"])
        for p in Part.query.order_by(Part.code):
            writer.writerow([p.code, p.part_type, p.category, p.specification, p.location, p.stock, p.min_stock, p.max_stock, p.stock_status])
    elif kind == "warnings":
        writer.writerow(["寿命编号", "备件编号", "设备", "分类", "安装日期", "到期日期", "剩余天数", "预警等级"])
        for item in Lifecycle.query.order_by(Lifecycle.installed_at):
            writer.writerow([item.serial_number, item.part.code, item.equipment.full_name, item.classification, item.installed_at.date(), item.due_date, item.remaining_days, item.warning_level])
    elif kind == "procurement":
        writer.writerow(["采购编号", "备件编号", "数量", "实时库存", "来源", "参考区间", "状态", "日期"])
        for item in Procurement.query.order_by(Procurement.created_at.desc()):
            writer.writerow([item.number, item.part.code, item.quantity, item.real_stock, item.source, item.reference_range, item.status, item.created_at])
    else:
        abort(404)
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={kind}-{date.today()}.csv"},
    )


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="当前账号没有此项审批权限"), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="您访问的内容不存在"), 404


def seed_database():
    if DEMO_MODE:
        User.query.filter_by(username="operator").delete()
    for username, password, display_name, role, department in DEMO_ACCOUNTS:
        user = User.query.filter_by(username=username).first()
        is_new = user is None
        if is_new:
            user = User(username=username, password_hash="", display_name=display_name)
            db.session.add(user)
        user.display_name = display_name
        user.department = department
        user.role = role
        user.active = True
        user.created_at = user.created_at or now()
        user.preferred_language = user.preferred_language or "zh"
        if DEMO_MODE or is_new:
            user.password_hash = generate_password_hash(password)
    if Equipment.query.count() == 0:
        db.session.add_all(
            [
                Equipment(line_name="一号标准烟分拣线", device_type="开箱机", location="一工位"),
                Equipment(line_name="一号标准烟分拣线", device_type="开箱机", location="三工位", status="检修中"),
                Equipment(line_name="二号标准烟分拣线", device_type="包装机", location="卧式机"),
                Equipment(line_name="一号异型烟分拣线", device_type="包装机", location="柜式机"),
                Equipment(line_name="二号异型烟分拣线", device_type="输送设备", location="主传送段"),
            ]
        )
    if Supplier.query.count() == 0:
        db.session.add_all(
            [
                Supplier(name="甲供应商", contact="陈经理 13800001111", effective_date=date(2026, 5, 26), expiry_date=date(2029, 5, 26), status="生效", score=96),
                Supplier(name="乙供应商", contact="李经理 13800002222", effective_date=date(2026, 5, 26), expiry_date=date(2029, 5, 26), status="生效", score=91),
                Supplier(name="丙供应商", contact="王经理 13800003333", effective_date=date(2026, 5, 26), expiry_date=date(2029, 5, 26), status="生效", score=88),
            ]
        )
    if Part.query.count() == 0:
        db.session.add_all(
            [
                Part(code="DD-DJ-YEJ8024", part_type="电动", category="电机", specification="YEJ8024", location="01-01-01", stock=1, min_stock=2, max_stock=7, classification="生产核心件", service_life_days=365, unit_price=300),
                Part(code="DD-DJ-DT90S4", part_type="电动", category="电机", specification="DT90S4", location="01-01-02", stock=5, min_stock=2, max_stock=7, classification="安全核心件", service_life_days=540, unit_price=420),
                Part(code="QD-QG-IC50B350", part_type="气动", category="气缸", specification="IC50B350", location="02-03-01", stock=0, min_stock=3, max_stock=8, classification="生产核心件", service_life_days=270, unit_price=200),
                Part(code="QD-QG-MAL20X100", part_type="气动", category="气缸", specification="MAL20*100", location="02-03-02", stock=9, min_stock=3, max_stock=8, classification="普通非核心件", service_life_days=180, unit_price=300),
                Part(code="CD-ZC-LMF16LUU", part_type="传动", category="轴承", specification="LMF16LUU", location="03-02-01", stock=6, min_stock=2, max_stock=10, classification="普通非核心件", service_life_days=200, unit_price=120),
                Part(code="CD-ZC-LM16UU", part_type="传动", category="轴承", specification="LM16uu", location="03-02-02", stock=4, min_stock=2, max_stock=10, classification="生产核心件", service_life_days=240, unit_price=150),
            ]
        )
    db.session.commit()

    if Lifecycle.query.count() == 0:
        parts_by_code = {p.code: p for p in Part.query.all()}
        equipment_items = Equipment.query.order_by(Equipment.id).all()
        demo = [
            ("SM-20260108-0001", "DD-DJ-DT90S4", 530),
            ("SM-20260318-0002", "QD-QG-IC50B350", 250),
            ("SM-20260202-0003", "CD-ZC-LMF16LUU", 185),
            ("SM-20260622-0004", "CD-ZC-LM16UU", 55),
        ]
        for index, (serial, code, used_days) in enumerate(demo):
            part = parts_by_code[code]
            db.session.add(
                Lifecycle(
                    serial_number=serial,
                    part=part,
                    equipment=equipment_items[index % len(equipment_items)],
                    installed_at=now() - timedelta(days=used_days),
                    expected_life_days=part.service_life_days,
                    classification=part.classification,
                )
            )
        db.session.add(AuditLog(user_name="系统", action="演示数据", detail="平台初始化完成"))
        db.session.commit()


def ensure_user_schema():
    columns = {row[1] for row in db.session.execute(text('PRAGMA table_info("user")')).fetchall()}
    migrations = {
        "active": 'ALTER TABLE "user" ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1',
        "created_at": 'ALTER TABLE "user" ADD COLUMN created_at DATETIME',
        "preferred_language": 'ALTER TABLE "user" ADD COLUMN preferred_language VARCHAR(5) DEFAULT "zh"',
    }
    for column, statement in migrations.items():
        if column not in columns:
            db.session.execute(text(statement))
    db.session.commit()


def init_app():
    with app.app_context():
        db.create_all()
        ensure_user_schema()
        seed_database()


init_app()


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5055")), debug=os.environ.get("FLASK_DEBUG") == "1")
