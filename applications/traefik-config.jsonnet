function(source_repo, source_target_revision) {
    apiVersion: "argoproj.io/v1alpha1",
    kind: "Application",
    metadata: {
        name: "w1-traefik-config",
        namespace: "argocd",
        finalizers: ["resources-finalizer.argocd.argoproj.io"],
        annotations: {
            "argocd.argoproj.io/sync-wave": "1",
        },
    },
    spec: {
        project: "appproj-nippon-koku",
        source: {
            repoURL: source_repo,
            targetRevision: source_target_revision,
            path: "manifests/traefik-config",
        },
        destination: {
            server: "https://kubernetes.default.svc",
        },
    },
}
