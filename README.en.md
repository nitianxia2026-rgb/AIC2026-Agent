# README · Project Guide (human-readable, start here)

> A map for the team lead and teammates. Operating rules for the AI assistant live in `CLAUDE.md` — the two files do not overlap.
> If you get lost, come back here. Last updated: 2026-09-15.

English | [简体中文](./README.md)

## Status at a glance

- **Product (switched on 09-07)**: *Toushou Zhinang* ("Bidder's Brain Trust") — an ad-spend strategy advisor for SMBs (AI + business / marketing track).
- **Current stage**: v0.2 blocker regression and freeze sprint; decision made that external data stays **out of the primary knowledge base** → semifinal (**9/19, online**).
- Progress and to-dos live in `00-进度看板.md` (the single source of truth for "where are we now").

## Document map

| File | What it is for | When to read it |
|---|---|---|
| `00-进度看板.md` | Current state + next actions + countdown | Skim before every work session |
| `README.md` / `README.en.md` | This file: the map | When you are lost |
| `01-赛事实录/赛事规程摘要.md` | Contest rules: format, scoring rubric, dates | Rule questions — check here, don't guess |
| `01-赛事实录/平台能力-助手模块.md` | What the platform can actually do (verified facts) | Platform-operations questions |
| `03-产出物/团队与分工.md` | Team, member profiles, mentors (Jiang Ying + Cheng Yong) | Team information |
| `03-产出物/投手智囊/01-产品文档-v1.0.md` | Product source document (origin of the ideas) | To see the whole product |
| `03-产出物/投手智囊/00-方案总览.md` | Index + platform adaptation + open set of references | To understand "how it lands" |
| `03-产出物/投手智囊/02-复赛蓝图-v0.md` | **Semifinal six-node plan (approved)** | When refining prompts / knowledge base |
| `03-产出物/投手智囊/07-复赛助手架构说明.md` | Six-node state machine, I/O, platform mapping | Architecture scoring and trial build |
| `03-产出物/投手智囊/08-数据准备与可追溯说明.md` | Data lineage, metric-scope boundaries, reproduction steps | Data scoring and defense evidence |
| `03-产出物/投手智囊/09-复赛90分钟操作Runbook.md` | Pre-upload, timing, fallbacks | Rehearsing the real contest |
| `04-协作区/02-当前阶段任务分配与群公告.md` | The single current task sheet: IDs, dependencies, templates, acceptance | Whole-team execution |
| `03-产出物/投手智囊/12-复赛工具选择与评分对齐.md` | Trade-offs between API/MCP and the calculator | Platform configuration decisions |
| `03-产出物/投手智囊/04-参考提炼笔记-cross-border-ai.md` | Lessons extracted from reference projects | Before writing SOPs / prompts |
| `04-协作区/` | **Teammate workspace: task sheet / data scripts / fixed delivery folders / trial-build assets** | Daily work and handoff (has its own README) |

**Archive**: `02-对话记录/` = conversation logs (old topic records were cleaned up on 09-07).

## Recommended reading order for the team lead (~10 minutes the first time)

1. This file (1 min)
2. `00-进度看板.md` → only the "next actions" section (1 min)
3. `01-产品文档-v1.0.md`, three key sections (6 min) — §1 positioning and boundaries, §4 architecture and stages, §8 planning inputs
4. The "platform adaptation" section of `00-方案总览.md` (2 min) — key differences between the product doc and the verified platform behavior

After that, the daily routine is just three things: **the board (every session) + the product doc (when refining) + the plan overview (when aligning)**.

## What needs your confirmation / action (as of 09-07)

1. Complete P0-01 per `00-进度看板.md`: the v0.2 test copy and environment record.
2. Run the 13-case blocker regression together with Chen Yutao; only proceed to the dual-version output comparison once there is no S0/S1.
3. Finish two 90-minute rehearsals on 9/17–18 and freeze the competition version.

## How the AI assistant uses these documents

1. `CLAUDE.md` is loaded automatically in every conversation (it contains the documentation discipline: each kind of information has exactly one owning file).
2. It reads the board first to locate the current state and this session's task.
3. It verifies on demand: rules → `01-赛事实录/`; product → `03-产出物/投手智囊/`; history → `02-对话记录/`.
4. It closes each session by updating the board and appending to the conversation log (no per-message spam).

**So you don't need to read every document — read your own handful, and I'll look up the rest.**
