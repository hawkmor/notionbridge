import React, { type ReactNode } from 'react';
import StatusIndicator, { type StatusType } from './StatusIndicator';

interface StepCardProps {
    stepNumber: number;
    title: string;
    statusText: string;
    statusType: StatusType;
    description: string;
    children: ReactNode;
}

const StepCard: React.FC<StepCardProps> = ({
    stepNumber,
    title,
    statusText,
    statusType,
    description,
    children,
}) => {
    return (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden transition-shadow hover:shadow-md">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100 bg-white/50 backdrop-blur-sm">
                <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-7 h-7 rounded-full bg-slate-100 text-slate-500 text-sm font-semibold">
                        {stepNumber}
                    </div>
                    <h2 className="text-base font-semibold text-slate-900">{title}</h2>
                </div>
                <StatusIndicator statusType={statusType} statusText={statusText} />
            </div>

            {/* Body */}
            <div className="p-6">
                <p className="text-sm text-slate-500 mb-6 max-w-lg leading-relaxed">
                    {description}
                </p>
                <div>{children}</div>
            </div>
        </div>
    );
};

export default StepCard;
