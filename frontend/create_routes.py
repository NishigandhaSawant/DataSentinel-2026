import os

base = "c:/Projects/DataSentinel/frontend/src/app/[sessionId]"

routes = ["detect", "insights", "clean", "compare", "edit", "visualize", "query", "report"]
components = ["Detection", "Insights", "Clean", "Compare", "ReviewEdit", "Visualizer", "Query", "ExportReport"]
paths = ["detection", "insights", "clean", "compare", "review-edit", "visualizer", "query", "export-report"]

for route, comp, path in zip(routes, components, paths):
    os.makedirs(f"{base}/{route}", exist_ok=True)
    
    props = ""
    if route == "insights":
        props = "cachedInsights={cachedInsights} onInsightsLoaded={setCachedInsights}"
    elif route == "clean":
        props = "recommendedMethod={recommendedMethod} cleaningRationale={cleaningRationale} onComplete={() => router.push(`/${sessionId}/compare`)}"
    elif route == "detect":
        props = "onNext={() => router.push(`/${sessionId}/insights`)}"
    elif route == "compare":
        props = "onNext={() => router.push(`/${sessionId}/edit`)}"

    page = f"""
"use client";
import {{ use }} from "react";
import {comp} from "@/components/{path}";
import {{ useSession }} from "../SessionProvider";
import {{ useRouter }} from "next/navigation";

export default function {comp}Page({{ params }}: {{ params: Promise<{{ sessionId: string }}> }}) {{
  const {{ sessionId }} = use(params);
  const {{ cachedInsights, setCachedInsights, recommendedMethod, cleaningRationale }} = useSession();
  const router = useRouter();
  
  return (
    <div className="w-full mt-10">
      <{comp} sessionId={{sessionId}} {props} />
    </div>
  );
}}
"""
    with open(f"{base}/{route}/page.tsx", "w") as f:
        f.write(page.strip())

print("Next.js App Router files fixed!")
