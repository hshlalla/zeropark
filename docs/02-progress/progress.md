---
doc_type: progress
project_id: zeropark_v2
status: in_progress
updated_at: 2026-06-09
---

# 진척 상황 (Zeropark V2 Enterprise)

기존 V1(PoC) 버전 개발을 100% 완료하고, 새로운 B2B 상용화(Enterprise) 규격인 V2 개발을 새롭게 시작합니다.

## 최근 완료된 작업
- V1 문서 초기화 완료
- V2 기획안(요구사항, 아키텍처, WBS) 도출 및 작성 완료

## 진행 중 / 다음 작업
- **Phase 1: 인프라 & 보안 컨테이너**
  - [ ] W-2-01: PostgreSQL DB 연동 (SQLAlchemy 셋업)
  - [ ] W-2-02: Auth 인증 계층(OAuth) 및 JWT 도입
  - [ ] W-2-03: Docker 기반 격리 샌드박스 

## 블로커 / 주요 리스크
- **Docker 호스트 통신**: 백엔드(FastAPI)가 호스트에서 동작할 때, 동적으로 Docker 컨테이너를 스핀업(Spin-up)하고 코드 결과를 읽어오는 파이프라인의 레이턴시 및 생명주기 관리 설계가 중요.
- **DB 마이그레이션**: 기존에 파일로 저장되던 로컬 아티팩트 및 설정들을 RDBMS 중심으로 어떻게 이관/매핑할 것인지 정의 필요.
