import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "../api/auth";
import { Logo } from "../components/ui/Logo";

export function RegisterPage() {
    const navigate = useNavigate();

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setSuccess("");

        if (password.length < 6) {
            setError("Password must be at least 6 characters.");
            return;
        }

        if (password !== confirmPassword) {
            setError("Passwords do not match.");
            return;
        }

        setLoading(true);

        try {
            const res = await authApi.register({ email, password });
            setSuccess(res.message);
            // After 3 seconds, redirect to login
            setTimeout(() => navigate("/login"), 3000);
        } catch (err: any) {
            const detail =
                err?.response?.data?.detail ?? err?.message ?? "Registration failed";
            setError(detail);
        } finally {
            setLoading(false);
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
                    <p className="text-text-muted mt-1 text-sm">Create a new account</p>
                </div>

                {/* Card */}
                <div className="bg-bg-card border border-border rounded-xl p-6 space-y-5 shadow-lg shadow-black/30">
                    {error && (
                        <div className="bg-error/10 border border-error/30 rounded-lg px-4 py-3 text-sm text-error">
                            {error}
                        </div>
                    )}

                    {success && (
                        <div className="bg-success/10 border border-success/30 rounded-lg px-4 py-3 text-sm text-success">
                            {success} — Redirecting to login…
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="space-y-1.5">
                            <label className="text-sm font-medium text-text-secondary">
                                Email
                            </label>
                            <input
                                id="register-email"
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
                                id="register-password"
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Minimum 6 characters"
                                className="w-full px-3 py-2.5 bg-bg-tertiary border border-border rounded-lg text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary-600 transition-colors"
                            />
                        </div>

                        <div className="space-y-1.5">
                            <label className="text-sm font-medium text-text-secondary">
                                Confirm Password
                            </label>
                            <input
                                id="register-confirm"
                                type="password"
                                required
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                placeholder="Re-enter your password"
                                className="w-full px-3 py-2.5 bg-bg-tertiary border border-border rounded-lg text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary-600 transition-colors"
                            />
                        </div>

                        <button
                            id="register-submit"
                            type="submit"
                            disabled={loading || !!success}
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
                                    Creating account…
                                </span>
                            ) : (
                                "Create Account"
                            )}
                        </button>
                    </form>

                    <div className="text-center text-sm text-text-muted">
                        Already have an account?{" "}
                        <Link
                            to="/login"
                            className="text-primary-400 hover:text-primary-300 font-medium"
                        >
                            Sign in
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
