import { Link } from "react-router-dom";
import type { MouseEvent } from "react";
import { ArrowUpRight, MessageSquareText } from "lucide-react";
import type { Intent } from "./types";
import "./styles.css";

export function openAssistant(event: MouseEvent, scope: { company?: number | string; application?: number | string; intent?: string }) {
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
  event.preventDefault();
  window.dispatchEvent(new CustomEvent("delo:assistant-open", { detail: scope }));
}

export function assistantUrl(
  scope: {
    company?: number | string;
    application?: number | string;
    intent?: Intent;
  } = {},
) {
  const q = new URLSearchParams();
  if (scope.company) q.set("company", String(scope.company));
  if (scope.application) q.set("application", String(scope.application));
  if (scope.intent) q.set("intent", scope.intent);
  return `/assistant${q.size ? `?${q}` : ""}`;
}

export function AssistantInvite({
  company,
  application,
  staff = false,
}: {
  company?: number | string;
  application?: number | string;
  staff?: boolean;
}) {
  return (
    <section className="assistant-invite">
      <div className="assistant-invite-visual">
        <MessageSquareText size={28} aria-hidden="true" />
      </div>
      <div>
        <h2>
          {staff
            ? "Второй взгляд на заявку"
            : "Есть вопрос? Давайте разберёмся."}
        </h2>
        <p>
          {staff
            ? "Сводка, недостающие сведения и черновик ответа — с опорой на данные заявки."
            : "Объясню рейтинг, помогу с заявкой и найду нужные материалы."}
        </p>
      </div>
      <Link
        className="button secondary"
        onClick={(event) => openAssistant(event, {company, application, intent: staff ? "application_review" : "chat"})}
        to={assistantUrl({
          company,
          application,
          intent: staff ? "application_review" : "chat",
        })}
      >
        Открыть помощника
        <ArrowUpRight size={17} />
      </Link>
    </section>
  );
}
