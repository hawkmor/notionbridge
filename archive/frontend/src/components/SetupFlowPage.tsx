import React, { type ReactNode } from 'react';

interface SetupFlowPageProps {
    title: string;
    subtitle: string;
    lang: 'en' | 'zh';
    onLangToggle: () => void;
    children: ReactNode;
    logoUrl?: string; // Optional logo image URL
}

const SetupFlowPage: React.FC<SetupFlowPageProps> = ({
    title,
    subtitle,
    lang,
    onLangToggle,
    children,
    logoUrl
}) => {
    return (
        <div className="min-h-screen bg-slate-50 py-12 px-4 font-sans text-slate-900">
            <div className="max-w-2xl mx-auto space-y-10">
                {/* Header */}
                <header className="text-center space-y-2 relative">
                    <div className="absolute top-0 right-0">
                        <button
                            onClick={onLangToggle}
                            className="text-xs font-medium text-slate-400 hover:text-slate-600 px-2 py-1 rounded border border-transparent hover:border-slate-200 transition-all font-mono"
                        >
                            {lang === 'en' ? '中文' : 'English'}
                        </button>
                    </div>

                    {/* Title with optional logo */}
                    <div className="flex items-center justify-center gap-3">
                        {logoUrl && (
                            <img
                                src={logoUrl}
                                alt="Logo"
                                className="w-10 h-10 object-contain"
                            />
                        )}
                        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
                    </div>

                    <p className="text-slate-500">{subtitle}</p>
                </header>

                {/* Main Content Flow */}
                <div className="space-y-6">
                    {children}
                </div>

                {/* Footer */}
                <footer className="text-center pt-8 pb-4">
                    <p className="text-xs text-slate-400">Secure Client-Side Processing • V 1.0.1</p>
                </footer>
            </div>
        </div>
    );
};

export default SetupFlowPage;
