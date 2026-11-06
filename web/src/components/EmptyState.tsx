import React from "react";
import { Inbox } from "lucide-react";
import { PillButton } from "./PillButton";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  className = "",
}) => {
  return (
    <div className={`empty-state-card ${className}`.trim()}>
      <div className="empty-state-icon" aria-hidden="true">
        {icon || <Inbox size={36} />}
      </div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-description">{description}</p>
      {actionLabel && onAction && (
        <div className="empty-state-action">
          <PillButton variant="primary" size="md" onClick={onAction}>
            {actionLabel}
          </PillButton>
        </div>
      )}
    </div>
  );
};

