# Hi-VideoSum Midterm Report — Overleaf Package

이 폴더는 `midterm_report.md`를 Overleaf에 바로 업로드해 컴파일할 수 있도록 변환한 LaTeX 패키지입니다.

## 포함된 파일

- `main.tex` — 보고서 본문 (LaTeX)
- `pipeline.png` — §3 Methodology에 삽입되는 파이프라인 다이어그램 (원본 `image.png` 복사본)
- `README.md` — 이 안내 파일

## Overleaf에서 컴파일하는 법

1. Overleaf에 로그인 → **New Project** → **Upload Project**
2. 이 `overleaf_package/` 폴더 전체를 zip으로 묶어 업로드
   (또는 폴더 안의 파일들을 직접 드래그)
3. 프로젝트가 열리면 좌상단 **Menu** → **Compiler** 를 **XeLaTeX** 로 변경
   - 한국어 폰트(`xeCJK` + Noto Serif CJK KR)를 사용하므로 pdfLaTeX은 동작하지 않습니다
4. **Recompile** 버튼 클릭

## 폰트 변경

Overleaf에는 `Noto Serif CJK KR` / `Noto Sans CJK KR` 가 기본 설치되어 있어 별도 폰트 업로드 없이 컴파일됩니다.
다른 한국어 폰트(예: `Nanum Myeongjo`, `KoPubWorld Batang`)를 쓰려면 `main.tex` 상단의 다음 줄을 수정하세요.

```latex
\setCJKmainfont{Noto Serif CJK KR}
\setCJKsansfont{Noto Sans CJK KR}
```

## 로컬에서 컴파일하는 법 (옵션)

```bash
xelatex main.tex
xelatex main.tex   # 참조(\ref) 두 번 빌드
```

또는 `latexmk` 사용:

```bash
latexmk -xelatex main.tex
```

## 채워 넣을 곳

- `\subsection{원시 데이터 통계}` (§2.3) — 원시 vs 2차 필터링 통계, 최종 요약 데이터셋 통계
- `\subsection*{C. 수집 채널 리스트}` — 80개 채널 전체 목록
