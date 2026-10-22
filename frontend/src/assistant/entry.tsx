import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { AgentState } from "@/components/ui/agent-state";
import type { Intent } from "./types";
import "./styles.css";

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
        <AgentState size="sm" status="idle" label="" aria-label="Помощник" />
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
