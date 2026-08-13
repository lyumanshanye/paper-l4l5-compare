#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    template = args.template.read_text(encoding="utf-8")
    style = re.search(r"<style>(.*?)</style>", template, flags=re.DOTALL).group(1)
    data = json.loads(args.results.read_text(encoding="utf-8"))
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = PAGE.replace("__STYLE__", style).replace("__PAYLOAD__", payload)
    args.out.write_text(html, encoding="utf-8")
    print(f"saved -> {args.out} ({len(html)} bytes)")


PAGE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>论文 L4 · L5 DeepSeek 效果审阅</title>
<style>__STYLE__
.tabbar,.reportlink,.guide-chip,.guide-pop{display:none!important}
.shell{grid-template-columns:300px minmax(0,1fr)}
header.mast{position:relative}
nav.rail{top:0;height:100vh}
.bk{grid-template-columns:28px minmax(0,1fr)}
.bk .dm{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;white-space:normal;overflow:hidden}
.bk .src{font-size:9.5px}
.strip{display:block;min-width:0}
.mcard{width:100%;max-width:none;flex:none}
.source-link{color:var(--accent);text-decoration:none}
.source-link:hover{text-decoration:underline}
@media(max-width:760px){.shell{grid-template-columns:1fr}nav.rail{height:auto}.strip{display:block;min-width:0}.mcard{width:100%}}
</style>
</head>
<body>
<header class="mast">
  <div class="mast-row">
    <div class="brand">
      <h1>论文洗数据管线 · <span class="pipe">L4 / L5</span> DeepSeek 审阅台</h1>
      <p>数据＝<b>K202607100001 论文批次</b>，固定种子抽取 30 篇可公开读取的真实论文。每篇精确定位标题与正文边界，抽取一个最多 <b>1024 token</b> 的论文段；同一段分别执行 <b>L4 生成式清洗</b>与 <b>L5 认知补全重写</b>。模型＝<b>DeepSeek-V4-Flash</b>。</p>
      <p class="tabnote">红＝删除，绿＝L4 修正，黄＝L5 新增。每条可由 CSV 行号、DOI 和公开 PDF 追溯。</p>
    </div>
    <div class="mast-tools">
      <div class="legend">
        <span class="lg"><span class="sw d"></span>L4 删除</span>
        <span class="lg"><span class="sw a"></span>L4 修正</span>
        <span class="lg"><span class="sw h"></span>L5 新增重写</span>
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
let cur=0, mode="all", renderSeq=0;
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
  const A=tokenize(aStr),B=tokenize(bStr),n=A.length,m=B.length,ak=A.map(normKey),bk=B.map(normKey),W=m+1;
  const dp=new Uint16Array((n+1)*W);
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)dp[i*W+j]=ak[i]===bk[j]?dp[(i+1)*W+j+1]+1:Math.max(dp[(i+1)*W+j],dp[i*W+j+1]);
  const ops=[];let del=0,ins=0,i=0,j=0;const push=(t,s)=>{const last=ops[ops.length-1];if(last&&last.t===t)last.s+=s;else ops.push({t,s})};
  while(i<n&&j<m){if(ak[i]===bk[j]){push("eq",A[i++]);j++}else if(dp[(i+1)*W+j]>=dp[i*W+j+1]){push("del",A[i]);if(isWord(A[i]))del++;i++}else{push("ins",B[j]);if(isWord(B[j]))ins++;j++}}
  while(i<n){push("del",A[i]);if(isWord(A[i]))del++;i++}while(j<m){push("ins",B[j]);if(isWord(B[j]))ins++;j++}return{ops,del,ins};
}
function renderDiff(diff,level){const cls=level==="l4"?"df-ins-l4":"df-ins-l5";return diff.ops.map(op=>op.t==="eq"?esc(op.s):op.t==="del"?'<del class="df-del">'+esc(op.s)+'</del>':'<span class="'+cls+'">'+esc(op.s)+'</span>').join("")}
function buildRail(){
  BOOKS.forEach((book,index)=>{const button=document.createElement("button");button.type="button";button.className="bk hard";button.innerHTML='<span class="n">'+pad2(book.idx)+'</span><span><span class="dm" title="'+esc(book.title)+'">'+esc(book.title)+'</span><span class="src">'+esc(book.source)+'</span></span>';button.onclick=()=>select(index);rail.appendChild(button)});
}
function syncHash(){history.replaceState(null,"","#book="+BOOKS[cur].idx+"&stage="+mode)}
function select(index){if(index<0||index>=BOOKS.length)return;cur=index;[...rail.querySelectorAll(".bk")].forEach((el,i)=>el.classList.toggle("on",i===index));render();main.scrollIntoView({block:"start"});syncHash()}
function render(){
  const book=BOOKS[cur],seq=++renderSeq,meta=book.metadata||{},tokenLabel=meta.segment_tokens||1024;
  main.innerHTML='<div class="bookhead"><div class="bighash">'+pad2(book.idx)+'</div><div class="meta"><div class="titlerow"><span class="dombadge">'+esc(book.domain||"Academic paper")+'</span><span class="srcmini">'+esc(book.source)+'</span></div><div class="booktitle">'+esc(book.title)+'</div></div><div class="nav-arrows"><button class="arrow" id="prevb" '+(cur===0?"disabled":"")+'>← 上一篇</button><button class="arrow" id="nextb" '+(cur===BOOKS.length-1?"disabled":"")+'>下一篇 →</button></div></div>'+
  '<div class="stagebar"><div class="segctl"><button data-m="all" class="'+(mode==="all"?"on":"")+'">全部 ②＋③</button><button data-m="l4" class="'+(mode==="l4"?"on":"")+'">仅 ② L4</button><button data-m="l5" class="'+(mode==="l5"?"on":"")+'">仅 ③ L5</button></div><span class="stage-hint"><a class="source-link" target="_blank" rel="noopener" href="'+esc(meta.pdf_url||"")+'">公开 PDF</a> · '+tokenLabel+' token</span></div>'+
  '<div class="orig" id="origp"><div class="panel-tag"><span class="step">①</span> 进 L4 前 · 论文正文段</div><div class="body">'+esc(book.seg)+'</div><button class="moretog" id="origmore">展开全文 ▾</button></div><div class="strip-wrap"><div class="strip stagewrap" id="strip" data-mode="'+mode+'"></div></div>';
  $("prevb").onclick=()=>select(cur-1);$("nextb").onclick=()=>select(cur+1);$("origmore").onclick=()=>{const open=$("origp").classList.toggle("open");$("origmore").textContent=open?"收起 ▴":"展开全文 ▾"};
  main.querySelectorAll(".segctl button").forEach(button=>button.onclick=()=>{mode=button.dataset.m;main.querySelectorAll(".segctl button").forEach(x=>x.classList.toggle("on",x===button));$("strip").dataset.mode=mode;syncHash()});
  const strip=$("strip");
  ORDER.forEach(model=>{const value=book.models[model],card=document.createElement("div");card.className="mcard";card.innerHTML='<div class="mcard-h"><span class="mname">'+esc(model)+'</span><span class="badge base">当前模型</span></div>';["l4","l5"].forEach(level=>{const stage=document.createElement("div");stage.className="stage "+level;stage.innerHTML='<div class="stage-h"><span class="step">'+(level==="l4"?"②":"③")+'</span>'+(level==="l4"?"过 L4 · 清洗":"过 L5 · 认知重写")+'<span class="stat" data-role="stat">…</span></div><div class="difftext" data-role="body"><span class="calc">计算 diff…</span></div>';card.appendChild(stage)});strip.appendChild(card);["l4","l5"].forEach(level=>setTimeout(()=>{if(seq!==renderSeq)return;const stage=card.querySelector(".stage."+level),diff=diffTokens(book.seg,value[level]);stage.querySelector('[data-role="body"]').innerHTML=renderDiff(diff,level);stage.querySelector('[data-role="stat"]').textContent=level==="l4"?"−"+diff.del+" 删 · +"+diff.ins+" 改":"+"+diff.ins+" 新增 · −"+diff.del+" 删"},0))});
}
buildRail();
const match=/book=(\d+)/.exec(location.hash),stage=/stage=(all|l4|l5)/.exec(location.hash);if(stage)mode=stage[1];if(match){const found=BOOKS.findIndex(book=>book.idx===+match[1]);if(found>=0)cur=found}select(cur);
document.addEventListener("keydown",event=>{if(event.key==="ArrowLeft")select(cur-1);if(event.key==="ArrowRight")select(cur+1)});
</script>
</body>
</html>'''


if __name__ == "__main__":
    main()
