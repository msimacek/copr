package org.fedoraproject.copr.client.cli;

import org.fedoraproject.copr.client.CoprConfiguration;
import org.fedoraproject.copr.client.CoprException;
import org.fedoraproject.copr.client.CoprSession;

public interface CliCommand
{
    public abstract void run( CoprSession session, CoprConfiguration configuration )
        throws CoprException;

}