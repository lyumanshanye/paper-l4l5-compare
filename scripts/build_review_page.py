#!/usr/bin/env python3
import argparse
import html
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--compare-results", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    template = args.template.read_text(encoding="utf-8")
    style = re.search(r"<style>(.*?)</style>", template, flags=re.DOTALL).group(1)
    data = json.loads(args.results.read_text(encoding="utf-8"))
    if args.compare_results:
        comparison = json.loads(args.compare_results.read_text(encoding="utf-8"))
        comparison_model = comparison["model"]
        comparison_books = {book["idx"]: book for book in comparison["books"]}
        missing = [book["idx"] for book in data["books"] if book["idx"] not in comparison_books]
        if missing:
            raise RuntimeError(f"comparison results missing paper IDs: {missing}")
        if comparison_model not in data["model_order"]:
            data["model_order"].append(comparison_model)
        for book in data["books"]:
            result = comparison_books[book["idx"]]
            book.setdefault("models", {})[comparison_model] = {"l5": result.get("l5", "")}
    model_order = data.get("model_order", [])
    data["books"] = [
        {
            **book,
            "models": {
                model: {
                    "l5": (book.get("models", {}).get(model) or {}).get("l5", "")
                }
                for model in model_order
            },
        }
        for book in data.get("books", [])
    ]
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    model_names = " vs ".join(model_order)
    page = (
        PAGE.replace("__STYLE__", style)
        .replace("__PAYLOAD__", payload)
        .replace("__MODEL_NAMES__", html.escape(model_names))
    )
    args.out.write_text(page, encoding="utf-8")
    print(f"saved -> {args.out} ({len(page)} bytes)")


PAGE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>论文 L5 双模型效果对比</title>
<style>__STYLE__
.tabbar,.reportlink,.guide-chip,.guide-pop{display:none!important}
.shell{grid-template-columns:300px minmax(0,1fr)}
header.mast{position:relative}
nav.rail{top:0;height:100vh}
.bk{grid-template-columns:28px minmax(0,1fr)}
.bk .dm{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;white-space:normal;overflow:hidden}
.bk .src{font-size:9.5px}
.strip{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;min-width:0}
.mcard{width:100%;max-width:none;flex:none}
.source-link{color:var(--accent);text-decoration:none}
.source-link:hover{text-decoration:underline}
@media(max-width:1000px){.strip{grid-template-columns:1fr}}
@media(max-width:760px){.shell{grid-template-columns:1fr}nav.rail{height:auto}.mcard{width:100%}}
</style>
</head>
<body>
<header class="mast">
  <div class="mast-row">
    <div class="brand">
      <h1>论文洗数据管线 · <span class="pipe">L5</span> 双模型审阅台</h1>
      <p>数据＝<b>K202607100001 论文批次</b>，固定种子抽取 30 篇可公开读取的真实论文。每篇使用完全相同的正文段与 <b>L5 认知补全 Prompt</b>。模型＝<b>__MODEL_NAMES__</b>。</p>
      <p class="tabnote">黄色＝L5 新增或改写，灰色删除线＝L5 删除。每条可由 CSV 行号、DOI 和公开 PDF 追溯。</p>
    </div>
    <div class="mast-tools">
      <div class="legend">
        <span class="lg"><span class="sw h"></span>L5 新增 / 改写</span>
      </div>
      <button class="themebtn" id="themebtn" type="button"><span id="themeicon">◐</span><span id="themelabel">主题</span></button>
    </div>
  </div>
</header>
<div class="shell">
  <nav class="rail" id="rail" aria-label="论文导航"><div class="rail-h">论文样本 · 30 篇</div></nav>
  <main id="main" aria-live="polite"></main>
</div>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
"use strict";
const $=id=>document.getElementById(id);
const DATA=JSON.parse($("payload").textContent), BOOKS=DATA.books, ORDER=DATA.model_order;
const rail=$("rail"), main=$("main");
let cur=0, renderSeq=0;
const diffCache=new Map();
const pad2=n=>String(n).padStart(2,"0");
const esc=s=>String(s??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
(function(){
  const root=document.documentElement;
  function paint(){const dark=root.dataset.theme?root.dataset.theme==="dark":matchMedia("(prefers-color-scheme:dark)").matches;$("themeicon").textContent=dark?"☾":"☀";$("themelabel").textContent=dark?"深色":"浅色"}
  $("themebtn").onclick=()=>{const dark=root.dataset.theme?root.dataset.theme==="dark":matchMedia("(prefers-color-scheme:dark)").matches;root.dataset.theme=dark?"light":"dark";paint()};paint();
})();
function tokenize(s){return String(s??"").match(/\s+|[^\s]+/g)||[]}
function normKey(t){if(/^\s+$/.test(t))return " ";return t.replace(/[“”„‟]/g,'"').replace(/[‘’‚‛]/g,"'").replace(/[–—―−]/g,"-")}
function isWord(t){return !/^\s+$/.test(t)}
function diffTokens(aStr,bStr){
  const cacheKey=aStr+"\u0000"+bStr;
  const cached=diffCache.get(cacheKey);
  if(cached)return cached;
  const A=tokenize(aStr),B=tokenize(bStr),n=A.length,m=B.length,ak=A.map(normKey),bk=B.map(normKey),W=m+1;
  const dp=new Uint16Array((n+1)*W);
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)dp[i*W+j]=ak[i]===bk[j]?dp[(i+1)*W+j+1]+1:Math.max(dp[(i+1)*W+j],dp[i*W+j+1]);
  const ops=[];let del=0,ins=0,i=0,j=0;const push=(t,s)=>{const last=ops[ops.length-1];if(last&&last.t===t)last.s+=s;else ops.push({t,s})};
  while(i<n&&j<m){if(ak[i]===bk[j]){push("eq",A[i++]);j++}else if(dp[(i+1)*W+j]>=dp[i*W+j+1]){push("del",A[i]);if(isWord(A[i]))del++;i++}else{push("ins",B[j]);if(isWord(B[j]))ins++;j++}}
  while(i<n){push("del",A[i]);if(isWord(A[i]))del++;i++}while(j<m){push("ins",B[j]);if(isWord(B[j]))ins++;j++}
  const result={ops,del,ins};diffCache.set(cacheKey,result);return result;
}
function renderDiff(diff,level){const cls=level==="l4"?"df-ins-l4":"df-ins-l5";return diff.ops.map(op=>op.t==="eq"?esc(op.s):op.t==="del"?'<del class="df-del">'+esc(op.s)+'</del>':'<span class="'+cls+'">'+esc(op.s)+'</span>').join("")}
function buildRail(){
  BOOKS.forEach((book,index)=>{const button=document.createElement("button");button.type="button";button.className="bk hard";button.innerHTML='<span class="n">'+pad2(book.idx)+'</span><span><span class="dm" title="'+esc(book.title)+'">'+esc(book.title)+'</span><span class="src">'+esc(book.source)+'</span></span>';button.onclick=()=>select(index);rail.appendChild(button)});
}
function syncHash(){history.replaceState(null,"","#book="+BOOKS[cur].idx)}
function select(index,scroll=true){if(index<0||index>=BOOKS.length)return;cur=index;[...rail.querySelectorAll(".bk")].forEach((el,i)=>el.classList.toggle("on",i===index));render();if(scroll)main.scrollIntoView({block:"start"});syncHash()}
function render(){
  const book=BOOKS[cur],seq=++renderSeq,meta=book.metadata||{},tokenLabel=meta.segment_tokens||1024;
  main.innerHTML='<div class="bookhead"><div class="bighash">'+pad2(book.idx)+'</div><div class="meta"><div class="titlerow"><span class="dombadge">'+esc(book.domain||"Academic paper")+'</span><span class="srcmini">'+esc(book.source)+'</span></div><div class="booktitle">'+esc(book.title)+'</div></div><div class="nav-arrows"><button class="arrow" id="prevb" '+(cur===0?"disabled":"")+'>← 上一篇</button><button class="arrow" id="nextb" '+(cur===BOOKS.length-1?"disabled":"")+'>下一篇 →</button></div></div>'+ 
  '<div class="stagebar"><span class="stage-hint"><a class="source-link" target="_blank" rel="noopener" href="'+esc(meta.pdf_url||"")+'">公开 PDF</a> · '+tokenLabel+' token</span></div>'+ 
  '<div class="orig" id="origp"><div class="panel-tag"><span class="step">①</span> L5 输入 · 论文正文段</div><div class="body">'+esc(book.seg)+'</div><button class="moretog" id="origmore">展开全文 ▾</button></div><div class="strip-wrap"><div class="strip stagewrap" id="strip"></div></div>';
  $("prevb").onclick=()=>select(cur-1);$("nextb").onclick=()=>select(cur+1);$("origmore").onclick=()=>{const open=$("origp").classList.toggle("open");$("origmore").textContent=open?"收起 ▴":"展开全文 ▾"};
  const strip=$("strip");
  ORDER.forEach(model=>{const value=(book.models[model]||{}).l5||"",card=document.createElement("div");card.className="mcard";card.innerHTML='<div class="mcard-h"><span class="mname">'+esc(model)+'</span><span class="badge base">对比模型</span></div>';const stage=document.createElement("div");stage.className="stage l5";stage.innerHTML='<div class="stage-h"><span class="step">②</span>过 L5 · 认知重写<span class="stat" data-role="stat">…</span></div><div class="difftext" data-role="body"><span class="calc">计算 diff…</span></div>';card.appendChild(stage);strip.appendChild(card);setTimeout(()=>{if(seq!==renderSeq)return;if(!value){stage.querySelector('[data-role="body"]').innerHTML='<div class="waitbox">暂无 L5 结果</div>';stage.querySelector('[data-role="stat"]').textContent="无结果";return}const diff=diffTokens(book.seg,value);stage.querySelector('[data-role="body"]').innerHTML=renderDiff(diff,"l5");stage.querySelector('[data-role="stat"]').textContent="+"+diff.ins+" 新增 · −"+diff.del+" 删"},0)});
}
buildRail();
const match=/book=(\d+)/.exec(location.hash);if(match){const found=BOOKS.findIndex(book=>book.idx===+match[1]);if(found>=0)cur=found}select(cur,false);
document.addEventListener("keydown",event=>{if(event.key==="ArrowLeft")select(cur-1);if(event.key==="ArrowRight")select(cur+1)});
</script>
</body>
</html>'''


if __name__ == "__main__":
    main()
