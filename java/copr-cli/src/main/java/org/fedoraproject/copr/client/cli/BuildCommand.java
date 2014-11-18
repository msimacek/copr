package org.fedoraproject.copr.client.cli;

import java.util.ArrayList;
import java.util.List;

import com.beust.jcommander.Parameter;
import com.beust.jcommander.ParameterException;

import org.fedoraproject.copr.client.BuildRequest;
import org.fedoraproject.copr.client.BuildResult;
import org.fedoraproject.copr.client.CoprConfiguration;
import org.fedoraproject.copr.client.CoprException;
import org.fedoraproject.copr.client.CoprSession;

public class BuildCommand
    implements CliCommand
{

    @Parameter( required = true )
    private final List<String> params = new ArrayList<>();

    @Override
    public void run( CoprSession session, CoprConfiguration configuration )
        throws CoprException
    {
        if ( params.size() < 2 )
        {
            throw new ParameterException( "Requires a project name and at least one SRPM URL" );
        }
        BuildRequest request = new BuildRequest();
        request.setUserName( configuration.getUsername() );
        request.setProjectName( params.get( 0 ) );
        for ( int i = 1; i < params.size(); i++ )
        {
            request.addSourceRpm( params.get( i ) );
        }
        BuildResult result = session.build( request );
        System.out.println( result.getMessage() );
        for ( long id : result.getBuildIds() )
        {
            System.out.println( "Build ID: " + id );
        }
    }

}
