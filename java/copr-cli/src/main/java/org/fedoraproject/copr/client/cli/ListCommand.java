package org.fedoraproject.copr.client.cli;

import java.util.ArrayList;
import java.util.List;

import com.beust.jcommander.Parameter;
import com.beust.jcommander.ParameterException;
import org.fedoraproject.copr.client.CoprConfiguration;
import org.fedoraproject.copr.client.CoprException;
import org.fedoraproject.copr.client.CoprSession;
import org.fedoraproject.copr.client.ListRequest;
import org.fedoraproject.copr.client.ListResult;
import org.fedoraproject.copr.client.ProjectId;

public class ListCommand
    implements CliCommand
{

    @Parameter( )
    private final List<String> names = new ArrayList<>();

    @Override
    public void run( CoprSession session, CoprConfiguration configuration )
        throws CoprException
    {
        if ( names.size() > 1 )
        {
            throw new ParameterException( "Expected only one argument" );
        }
        String username = names.size() == 1 ? names.get( 0 ) : configuration.getUsername();
        ListRequest request = new ListRequest();
        request.setUserName( username );
        ListResult result = session.list( request );
        for ( ProjectId id : result.getProjects() )
        {
            System.out.println( id.getProjectName() );
        }
    }

}
