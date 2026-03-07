import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "../api/auth";
import { useAuthStore } from "../stores/authStore";
import { Logo } from "../components/ui/Logo";

export function LoginPage() {
    const navigate = useNavigate();
    const login = useAuthStore((s) => s.login);

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    // Resend verification state
    const [resendLoading, setResendLoading] = useState(false);
    const [resendMsg, setResendMsg] = useState("");
    const [resendCooldown, setResendCooldown] = useState(false);

    const isVerificationError =
        error.toLowerCase().includes("not verified") ||
        error.toLowerCase().includes("email not verified");

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setResendMsg("");
        setLoading(true);

        try {
            const res = await authApi.login({ email, password });
            login(res.access_token, email);
            navigate("/", { replace: true });
        } catch (err: any) {
            const detail =
                err?.response?.data?.detail ?? err?.message ?? "Login failed";
            setError(detail);
        } finally {
            setLoading(false);
        }
    };

    const handleResend = async () => {
        if (!email || resendCooldown) return;
        setResendLoading(true);
        setResendMsg("");

        try {
            const res = await authApi.resendVerification(email);
            setResendMsg(res.message);
            // 60-second cooldown to prevent spam
            setResendCooldown(true);
            setTimeout(() => setResendCooldown(false), 60000);
        } catch (err: any) {
            const detail =
                err?.response?.data?.detail ?? "Failed to resend. Try again later.";
            setResendMsg(detail);
        } finally {
            setResendLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-bg-primary p-4">
            <div className="w-full max-w-md animate-slide-up">
                {/* Header */}
                <div className="text-center mb-8">
                    <Logo size={64} className="mx-auto mb-4 rounded-xl" />
                    <h1 className="text-3xl font-bold text-white tracking-tight">
                        RxTract
                    </h1>
                    <p className="text-text-muted mt-1 text-sm">
                        Sign in to your account
                    </p>
                </div>

                {/* Card */}
                <div className="bg-bg-card border border-border rounded-xl p-6 space-y-5 shadow-lg shadow-black/30">
                    {error && (
                        <div className="bg-error/10 border border-error/30 rounded-lg px-4 py-3 text-sm text-error">
                            <p>{error}</p>
                            {isVerificationError && (
                                <div className="mt-3 pt-3 border-t border-error/20">
                                    <button
                                        type="button"
                                        onClick={handleResend}
                                        disabled={resendLoading || resendCooldown}
                                        className="text-primary-400 hover:text-primary-300 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium underline underline-offset-2 transition-colors"
                                    >
                                        {resendLoading
                                            ? "Sending…"
                                            : resendCooldown
                                                ? "Email sent — check your inbox"
                                                : "Resend verification email"}
                                    </button>
                                    {resendMsg && (
                                        <p className="mt-2 text-xs text-text-secondary">
                                            {resendMsg}
                                        </p>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="space-y-1.5">
                            <label className="text-sm font-medium text-text-secondary">
                                Email
                            </label>
                            <input
                                id="login-email"
                                type="email"
                                required
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="you@example.com"
                                className="w-full px-3 py-2.5 bg-bg-tertiary border border-border rounded-lg text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary-600 transition-colors"
                            />
                        </div>

                        <div className="space-y-1.5">
                            <label className="text-sm font-medium text-text-secondary">
                                Password
                            </label>
                            <input
                                id="login-password"
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="••••••••"
                                className="w-full px-3 py-2.5 bg-bg-tertiary border border-border rounded-lg text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary-600 transition-colors"
                            />
                        </div>

                        <button
                            id="login-submit"
                            type="submit"
                            disabled={loading}
                            className="w-full py-2.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
                        >
                            {loading ? (
                                <span className="inline-flex items-center gap-2">
                                    <svg
                                        className="animate-spin h-4 w-4"
                                        viewBox="0 0 24 24"
                                        fill="none"
                                    >
                                        <circle
                                            className="opacity-25"
                                            cx="12"
                                            cy="12"
                                            r="10"
                                            stroke="currentColor"
                                            strokeWidth="4"
                                        />
                                        <path
                                            className="opacity-75"
                                            fill="currentColor"
                                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                                        />
                                    </svg>
                                    Signing in…
                                </span>
                            ) : (
                                "Sign In"
                            )}
                        </button>
                    </form>

                    <div className="text-center text-sm text-text-muted">
                        Don&apos;t have an account?{" "}
                        <Link
                            to="/register"
                            className="text-primary-400 hover:text-primary-300 font-medium"
                        >
                            Create one
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
