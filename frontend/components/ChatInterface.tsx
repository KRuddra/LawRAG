'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Scale } from 'lucide-react';
import { useChat } from '../hooks/useChat';
import MessageBubble from './MessageBubble';
import LoadingSkeleton from './LoadingSkeleton';
import InputDock from './InputDock';
import ConfidenceBadge from './ConfidenceBadge';
import ExportButton from './ExportButton';
import {
  CountryCode,
  DEFAULT_COUNTRY,
  DEFAULT_JURISDICTION_ID,
  federalFor,
} from '../lib/jurisdictions';

interface ChatInterfaceProps {
  initialQuery?: string;
}

export default function ChatInterface({ initialQuery }: ChatInterfaceProps) {
  const [input, setInput] = useState('');
  const [lastQuery, setLastQuery] = useState<string>('');
  const [country, setCountry] = useState<CountryCode>(DEFAULT_COUNTRY);
  const [jurisdiction, setJurisdiction] = useState<string>(DEFAULT_JURISDICTION_ID);
  const [categories, setCategories] = useState<string[]>([]);
  const { messages, loading, sendMessage } = useChat();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    if (initialQuery && messages.length === 0) {
      setInput(initialQuery);
      handleSend(initialQuery);
    }
  }, [initialQuery]);

  // Changing country resets the jurisdiction to that country's federal layer.
  const handleCountryChange = (next: CountryCode) => {
    setCountry(next);
    const fed = federalFor(next);
    if (fed) setJurisdiction(fed.id);
  };

  const toggleCategory = (value: string) =>
    setCategories((prev) =>
      prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value],
    );

  const handleSend = async (message?: string) => {
    const messageToSend = message || input;
    if (!messageToSend.trim() || loading) return;

    setLastQuery(messageToSend);
    if (!message) setInput('');
    await sendMessage(messageToSend, { jurisdiction, categories });
  };

  const latestAiMessage = messages.filter((m) => m.role === 'ai').slice(-1)[0];
  const latestResponse = latestAiMessage
    ? { confidence: latestAiMessage.confidence ?? 0.5, flags: latestAiMessage.flags ?? [] }
    : null;

  const isEmpty = messages.length === 0 && !loading;

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <div className="wordmark">
          <span className="wordmark-badge">
            <Scale size={18} />
          </span>
          <div>
            <h1 className="wordmark-title">Legal Chat</h1>
            <p className="wordmark-sub">Statutes &amp; regulations · US &amp; Canada</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {latestResponse && (
            <>
              <ConfidenceBadge confidence={latestResponse.confidence} />
              {latestResponse.flags.length > 0 && (
                <div className="flex gap-2">
                  {latestResponse.flags.map((flag, i) => (
                    <span
                      key={i}
                      className="rounded border border-yellow-800 bg-yellow-900/20 px-2 py-1 text-xs text-yellow-400"
                    >
                      {flag}
                    </span>
                  ))}
                </div>
              )}
            </>
          )}
          {messages.length > 0 && <ExportButton messages={messages} />}
        </div>
      </div>

      <div className="chat-feed">
        {isEmpty ? (
          <div className="empty-state">
            <span className="empty-badge">
              <Scale size={28} />
            </span>
            <h2 className="empty-title">What does the law say?</h2>
            <p className="empty-sub">
              Pick a jurisdiction and ask about statutes, regulations, or case law. Answers are
              scoped to the jurisdiction you choose — and its co-applicable federal layer.
            </p>
          </div>
        ) : (
          messages.map((message) => (
            <MessageBubble key={message.id || Date.now()} message={message} query={lastQuery} />
          ))
        )}
        {loading && <LoadingSkeleton />}
        <div ref={endRef} />
      </div>

      <InputDock
        input={input}
        onInputChange={setInput}
        onSend={handleSend}
        disabled={loading}
        country={country}
        jurisdiction={jurisdiction}
        categories={categories}
        onCountryChange={handleCountryChange}
        onJurisdictionChange={setJurisdiction}
        onToggleCategory={toggleCategory}
        onClearCategories={() => setCategories([])}
      />
    </div>
  );
}
