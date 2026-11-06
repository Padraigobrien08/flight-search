"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type DynamicToolUIPart } from "ai";
import { PlaneIcon } from "lucide-react";
import { useState } from "react";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  type PromptInputMessage,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { Tool, ToolContent, ToolHeader, ToolInput, ToolOutput } from "@/components/ai-elements/tool";
import { ItineraryResults } from "@/components/flights/itinerary-results";
import type { ToolOutput as FlightToolOutput } from "@/lib/types";

const SUGGESTIONS = [
  "Edinburgh to Lima, out around 21–24 May 2027, home from La Paz the week of 6 June",
  "I'd happily pay £150 more for a night in Madrid instead of a long connection",
  "London to Lima in late May, cheapest that doesn't land in the middle of the night",
];

const TOOL_LABELS: Record<string, string> = {
  plan_trip: "Searching hubs, dates and ticket types",
  search_route: "Checking one route",
  set_preferences: "Updating your preferences",
};

function ToolPart({ part }: { part: DynamicToolUIPart }) {
  const output = part.state === "output-available" ? (part.output as FlightToolOutput) : null;
  if (output?.kind === "plan") {
    return <ItineraryResults result={output.result} />;
  }
  if (part.toolName === "plan_trip" && (part.state === "input-available" || part.state === "input-streaming")) {
    return <Shimmer className="text-sm">{`${TOOL_LABELS.plan_trip}…`}</Shimmer>;
  }
  return (
    <Tool>
      <ToolHeader state={part.state} title={TOOL_LABELS[part.toolName] ?? part.toolName} toolName={part.toolName} type="dynamic-tool" />
      <ToolContent>
        <ToolInput input={part.input} />
        <ToolOutput errorText={part.state === "output-error" ? part.errorText : undefined} output={output} />
      </ToolContent>
    </Tool>
  );
}

export default function Page() {
  const [input, setInput] = useState("");
  const { messages, sendMessage, status, stop, error } = useChat({
    transport: new DefaultChatTransport({ api: "/api/chat" }),
  });

  const submit = (message: PromptInputMessage) => {
    const text = message.text?.trim();
    if (!text) return;
    sendMessage({ text });
    setInput("");
  };

  return (
    <main className="mx-auto flex h-dvh w-full max-w-3xl flex-col px-4">
      <header className="flex items-center gap-2 py-4">
        <PlaneIcon className="size-5" />
        <h1 className="font-semibold">Value-ranked flight search</h1>
      </header>

      <Conversation>
        <ConversationContent>
          {messages.length === 0 ? (
            <ConversationEmptyState
              description="Describe the trip and what you care about. Results are ranked by what each journey is worth to you, not just price."
              icon={<PlaneIcon className="size-8" />}
              title="Where are you going?"
            />
          ) : (
            messages.map((message) => (
              <Message from={message.role} key={message.id}>
                <MessageContent className={message.role === "user" ? "ml-auto w-fit rounded-2xl bg-secondary px-4 py-2" : "w-full"}>
                  {message.parts.map((part, i) => {
                    const key = `${message.id}-${i}`;
                    if (part.type === "text") {
                      return <MessageResponse key={key}>{part.text}</MessageResponse>;
                    }
                    if (part.type === "dynamic-tool") {
                      return <ToolPart key={key} part={part} />;
                    }
                    return null;
                  })}
                </MessageContent>
              </Message>
            ))
          )}
          {status === "submitted" && <Shimmer className="text-sm">Thinking…</Shimmer>}
          {error && <div className="rounded-lg border border-destructive/50 p-3 text-destructive text-sm">{error.message}</div>}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="flex flex-col gap-3 py-4">
        {messages.length === 0 && (
          <Suggestions>
            {SUGGESTIONS.map((s) => (
              <Suggestion key={s} onClick={(text) => sendMessage({ text })} suggestion={s} />
            ))}
          </Suggestions>
        )}
        <PromptInput onSubmit={submit}>
          <PromptInputBody>
            <PromptInputTextarea
              onChange={(e) => setInput(e.target.value)}
              placeholder="Edinburgh to Lima, late May, home from La Paz…"
              value={input}
            />
          </PromptInputBody>
          <PromptInputFooter className="justify-end">
            <PromptInputSubmit disabled={!input.trim() && status === "ready"} onStop={stop} status={status} />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </main>
  );
}
