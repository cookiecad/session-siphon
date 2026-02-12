import { NextRequest, NextResponse } from "next/server";
import { searchMessages } from "@/lib/typesense";
import type { MessageFilters, PaginationOptions } from "@/lib/types";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const query: string = body.query ?? "*";
    const filters: MessageFilters = body.filters ?? {};
    const pagination: PaginationOptions = body.pagination ?? {};

    const results = await searchMessages(query, filters, pagination);
    return NextResponse.json(results);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Search failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
