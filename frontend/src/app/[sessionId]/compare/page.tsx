"use client";
import { use } from "react";
import Compare from "@/components/compare";
import { useSession } from "../SessionProvider";
import { useRouter } from "next/navigation";

export default function ComparePage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const router = useRouter();
  
  return (
    <div className="w-full mt-10">
      <Compare sessionId={sessionId} />
      <div className="mt-8 flex justify-end"><button onClick={() => router.push(`/${sessionId}/edit`)} className="px-6 py-3 bg-white text-black font-medium rounded-xl hover:bg-neutral-200 transition-colors">Review &rarr;</button></div>
    </div>
  );
}