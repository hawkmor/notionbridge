import React from 'react';

export type StatusType = 'disconnected' | 'connected' | 'waiting' | 'valid' | 'ready' | 'running';

interface StatusIndicatorProps {
    statusType: StatusType;
    statusText: string;
}

const StatusIndicator: React.FC<StatusIndicatorProps> = ({ statusType, statusText }) => {
    const getStatusColor = (type: StatusType) => {
        switch (type) {
            case 'connected':
            case 'valid':
                return 'bg-green-100 text-green-700';
            case 'ready':
            case 'running':
                return 'bg-blue-100 text-blue-700';
            case 'waiting':
            case 'disconnected':
            default:
                return 'bg-slate-100 text-slate-500';
        }
    };

    return (
        <span className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(statusType)}`}>
            {statusText}
        </span>
    );
};

export default StatusIndicator;
