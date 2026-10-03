export default function ErrorBanner({ message }: { message: string }) {
  return (
    <p className="error-banner" role="alert">
      {message}
    </p>
  );
}
