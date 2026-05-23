from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass


# ==================================================
# 新增：子域名和目标管理相关模型
# ==================================================

class DomainTarget(Base):
    """主域名目标表"""
    __tablename__ = "domain_targets"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String, index=True, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending, scanning, completed, failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # 关联
    subdomains: Mapped[list["Subdomain"]] = relationship(back_populates="domain_target", cascade="all, delete-orphan")


class Subdomain(Base):
    """发现的子域名表"""
    __tablename__ = "subdomains"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain_target_id: Mapped[int] = mapped_column(ForeignKey("domain_targets.id"), index=True)
    subdomain: Mapped[str] = mapped_column(String, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending, testing, tested, vulnerable
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 发现来源
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # 关联
    domain_target: Mapped["DomainTarget"] = relationship(back_populates="subdomains")
    scan_results: Mapped[list["ScanResult"]] = relationship(back_populates="subdomain", cascade="all, delete-orphan")


class ScanResult(Base):
    """扫描结果表"""
    __tablename__ = "scan_results"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subdomain_id: Mapped[int] = mapped_column(ForeignKey("subdomains.id"), index=True)
    scan_type: Mapped[str] = mapped_column(String)  # dirsearch, nuclei, sqlmap, custom
    tool_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # success, failed, partial
    findings: Mapped[Optional[JSON]] = mapped_column(JSON, nullable=True)
    raw_output: Mapped[Optional[Text]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # 关联
    subdomain: Mapped["Subdomain"] = relationship(back_populates="scan_results")

class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # op_id
    name: Mapped[str] = mapped_column(String, nullable=True)   # task_name
    goal: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending, running, completed, failed, stopped
    sort_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # For custom sorting
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    sort_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    nodes: Mapped[list["GraphNodeModel"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    edges: Mapped[list["GraphEdgeModel"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    logs: Mapped[list["EventLogModel"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    interventions: Mapped[list["InterventionModel"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    scope_rules: Mapped[list["ScopeRuleModel"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class GraphNodeModel(Base):
    __tablename__ = "graph_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    
    node_id: Mapped[str] = mapped_column(String, index=True) # The ID used in NetworkX (e.g. "subtask_1")
    graph_type: Mapped[str] = mapped_column(String)  # 'task' or 'causal'
    
    type: Mapped[str] = mapped_column(String, nullable=True) # subtask, action, Evidence, etc.
    status: Mapped[str] = mapped_column(String, nullable=True)
    
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default={}) # Stores all node attributes
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    session: Mapped["SessionModel"] = relationship(back_populates="nodes")

class GraphEdgeModel(Base):
    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    
    source_node_id: Mapped[str] = mapped_column(String)
    target_node_id: Mapped[str] = mapped_column(String)
    
    graph_type: Mapped[str] = mapped_column(String) # 'task' or 'causal'
    relation_type: Mapped[str] = mapped_column(String, nullable=True) # dependency, caused_by...
    
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["SessionModel"] = relationship(back_populates="edges")

class EventLogModel(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    
    event_type: Mapped[str] = mapped_column(String) # thought, tool_call, tool_result, status_change
    content: Mapped[Dict[str, Any]] = mapped_column(JSON)
    
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["SessionModel"] = relationship(back_populates="logs")

class InterventionModel(Base):
    __tablename__ = "interventions"

    id: Mapped[str] = mapped_column(String, primary_key=True) # unique ID for the request
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    
    type: Mapped[str] = mapped_column(String) # e.g., "plan_approval", "branch_replan_approval"
    status: Mapped[str] = mapped_column(String, default="pending") # pending, approved, rejected, modified
    
    request_data: Mapped[Dict[str, Any]] = mapped_column(JSON) # The data Agent requested approval for
    response_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True) # User's decision
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    session: Mapped["SessionModel"] = relationship(back_populates="interventions")


class ScopeRuleModel(Base):
    """作用域规则表"""
    __tablename__ = "scope_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    scope_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    session: Mapped["SessionModel"] = relationship(back_populates="scope_rules")


class ReconRecord(Base):
    """侦察记录表，存储各阶段收集到的原始情报"""
    __tablename__ = "recon_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    record_type: Mapped[str] = mapped_column(String, index=True)
    target: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    source_step_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskPolicy(Base):
    """任务策略表，存储解析后的测试策略"""
    __tablename__ = "task_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String, index=True, unique=True)
    raw_policy: Mapped[str] = mapped_column(Text)
    parsed_policy: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    parse_status: Mapped[str] = mapped_column(String, default="pending")
    parse_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )