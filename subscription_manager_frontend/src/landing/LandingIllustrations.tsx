import { Check, Zap } from 'lucide-react'

export function SubscriptionStack() {
  return <div className="lp-subscription-stack" aria-hidden="true">
    <div className="lp-stack-card lp-stack-card-back"><span>YOUR FAVORITES</span><span>Music. Movies. More.</span></div>
    <div className="lp-stack-card lp-stack-card-middle"><span>UP NEXT</span><span>All accounted for.<Check size={21}/></span></div>
    <div className="lp-stack-card lp-stack-card-front">
      <div><Zap size={28} fill="currentColor" strokeWidth={2.5}/><strong>subly.</strong></div>
      <span>Less scattered.<br/>More sorted.</span>
      <div className="lp-stack-card-footer"><span>THE WHOLE PICTURE</span><span>✳</span></div>
    </div>
  </div>
}

export function ProcessThread() {
  return <>
    <svg className="lp-process-thread lp-process-thread-wide" viewBox="0 0 1200 400" fill="none" preserveAspectRatio="none" aria-hidden="true"><path d="M-40 20C60-25 90 196 280 168S398 42 548 88 700 355 906 248 1076 101 1240 166"/></svg>
    <svg className="lp-process-thread lp-process-thread-narrow" viewBox="0 0 600 700" fill="none" preserveAspectRatio="none" aria-hidden="true"><path d="M-20 45C80 0 215 171 345 130S566 145 566 310 29 311 28 480 209 516 340 564 485 680 620 610"/></svg>
  </>
}
